# MiniMax 链接分析器

一个简洁网页工具：输入 MiniMax API Key、目标链接（可选 GroupId / 模型）后按回车，后端抓取网页文本并调用 MiniMax 返回分析报告。

## 功能

- 极简 UI：API Key、GroupId（可选）、模型（可选）、链接输入框
- 链接输入框按回车触发分析
- 自动抓取链接页面文本（移除 script/style/noscript）
- 调用 MiniMax 生成结构化中文报告
- 基于 Python 标准库实现，无需额外依赖

## 本地运行

```bash
python app.py
```

打开：`http://localhost:8000`

## 使用方法

1. 输入 MiniMax API Key（必填）。
2. 如有需要，填写 GroupId 和模型名（可选）。
3. 输入要分析的链接并按回车。
4. 页面会显示分析报告。

## 注意事项

- API Key / GroupId / 模型会保存到浏览器 `sessionStorage`（仅当前会话），不会写入服务器文件。
- 某些网站可能阻止抓取或需要登录，分析结果会受影响。
- 默认接口为 `https://api.minimax.chat/v1/text/chatcompletion_v2`；如填写 GroupId，会自动拼接为 `?GroupId=...`。
