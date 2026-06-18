# AI 辅助投研工作流工具（Python MVP）

这是根据 `PRD_AI_Investment_Research_MVP_NoAuth.md` 实现的 Python / Streamlit 无登录注册 MVP。

## 功能

- 项目创建、选择、删除
- BP 上传 / 粘贴文本
- TXT、PDF、DOCX、PPTX 文档解析
- OpenAI-compatible LLM 分析 BP
- BP 陈述、最重要看点、关键假设、验证任务生成
- 补充材料验证与任务状态更新
- 手动修改验证任务状态和备注
- 投资 memo 预览和 Markdown 下载

## 安装

```bash
python3 -m pip install -r requirements.txt
```

## 配置 LLM

第一版真实 LLM 优先。未配置 `LLM_API_KEY` 时，应用可以打开，但不会写入半成品 AI 分析。

```bash
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_API_KEY="你的 API Key"
export LLM_MODEL="gpt-4o-mini"
```

## 启动

```bash
python3 -m streamlit run app.py --server.port 4200
```

打开：

```text
http://localhost:4200
```

如果 4200 端口已被占用，可换端口：

```bash
python3 -m streamlit run app.py --server.port 4215
```

## 测试

```bash
python3 -m unittest discover -s tests
```

## 使用 test_doc 做保密验收

默认验收不会把 `test_doc/` 内容发送给外部模型，只检查文件格式、本地解析、LLM 配置和单元测试：

```bash
python3 scripts/readiness_check.py
```

只有明确允许把测试 BP 内容发送给配置的 LLM 时，才使用：

```bash
python3 scripts/readiness_check.py --send-to-llm
```

## 数据

- SQLite 数据库：`data/app.db`
- 上传文件：`uploads/`
- 第一版无登录注册、无用户权限、无 `owner_id`。
