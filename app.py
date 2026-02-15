import json
import re
from html import unescape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).parent
INDEX_FILE = BASE_DIR / "templates" / "index.html"
STYLE_FILE = BASE_DIR / "static" / "style.css"

MINIMAX_API_BASE = "https://api.minimax.chat/v1/text/chatcompletion_v2"
DEFAULT_MINIMAX_MODEL = "MiniMax-Text-01"
MAX_SOURCE_CHARS = 12000


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def strip_html(raw_html: str) -> str:
    cleaned = re.sub(r"<script[\\s\\S]*?</script>|<style[\\s\\S]*?</style>|<noscript[\\s\\S]*?</noscript>", "", raw_html, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", cleaned)
    text = unescape(re.sub(r"\n+", "\n", text)).strip()
    return text[:MAX_SOURCE_CHARS]


def fetch_url_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (WebAnalyzerBot)"})
    with urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    return strip_html(body)


def extract_minimax_text(payload: dict) -> str:
    if isinstance(payload.get("reply"), str):
        return payload["reply"]

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]

    base_resp = payload.get("base_resp")
    if isinstance(base_resp, dict):
        status_msg = base_resp.get("status_msg")
        if status_msg:
            raise ValueError(f"MiniMax 返回错误：{status_msg}")

    raise ValueError("MiniMax 返回格式无法解析")


def build_minimax_url(group_id: str) -> str:
    group = group_id.strip()
    if not group:
        return MINIMAX_API_BASE
    return f"{MINIMAX_API_BASE}?{urlencode({'GroupId': group})}"


def analyze_with_minimax(url: str, content: str, api_key: str, group_id: str, model: str) -> str:
    instruction = (
        "你是一个网页内容分析助手。请基于我提供的网页文本输出结构化分析报告，"
        "要求中文回答，包含：\n"
        "1) 一句话总结\n"
        "2) 核心观点（3-5条）\n"
        "3) 关键信息/数据点\n"
        "4) 风险与可信度判断\n"
        "5) 可执行建议\n"
        "如果内容不足，请明确说明不确定性。"
    )

    payload = {
        "model": model or DEFAULT_MINIMAX_MODEL,
        "messages": [
            {
                "sender_type": "USER",
                "text": f"{instruction}\n\n目标链接：{url}\n\n网页内容：\n{content}",
            }
        ],
        "stream": False,
    }

    req = Request(
        build_minimax_url(group_id),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return extract_minimax_text(data)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._send_file(INDEX_FILE, "text/html; charset=utf-8")
            return

        if self.path == "/static/style.css":
            self._send_file(STYLE_FILE, "text/css; charset=utf-8")
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path != "/analyze":
            self.send_error(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"

        try:
            body = json.loads(raw)
            url = str(body.get("url", "")).strip()
            api_key = str(body.get("apiKey", "")).strip()
            group_id = str(body.get("groupId", "")).strip()
            model = str(body.get("model", DEFAULT_MINIMAX_MODEL)).strip() or DEFAULT_MINIMAX_MODEL

            if not is_valid_url(url):
                self._send_json(400, {"error": "请输入有效的 http/https 链接"})
                return

            if not api_key:
                self._send_json(400, {"error": "请先在页面中填写 MiniMax API Key"})
                return

            source_text = fetch_url_text(url)
            if not source_text:
                self._send_json(422, {"error": "抓取成功但未提取到可分析文本"})
                return

            report = analyze_with_minimax(url, source_text, api_key, group_id, model)
            self._send_json(200, {"report": report})
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            message = f"请求失败：{exc.reason}"
            if details:
                message = f"{message} | {details[:300]}"
            self._send_json(502, {"error": message})
        except URLError as exc:
            self._send_json(502, {"error": f"网络异常：{exc.reason}"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": f"服务异常：{exc}"})

    def _send_file(self, filepath: Path, content_type: str):
        content = filepath.read_text(encoding="utf-8")
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server():
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("Server started at http://0.0.0.0:8000")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
