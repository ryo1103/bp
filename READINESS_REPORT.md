# 本地验收报告：test_doc 保密模式

生成时间：2026-06-18

## 结论

当前项目已通过 `test_doc` 真实端到端验收：系统能够解析测试 BP、调用 DeepSeek、生成结构化投研分析、校验来源并生成 memo。

本次真实 AI 验收命令：

```bash
python3 scripts/readiness_check.py --send-to-llm
```

## 已验证通过

- `test_doc/` 已加入 `.gitignore`，不会进入版本管理。
- `.env` 已加入 `.gitignore`，不会泄露 API key。
- DeepSeek 环境配置存在：
  - `LLM_BASE_URL`: `https://api.deepseek.com`
  - `LLM_MODEL`: `deepseek-v4-flash`
  - `LLM_API_KEY`: 已配置
- 单元测试通过：

```text
Ran 5 tests OK
```

- `test_doc` 本地解析通过：
  - 文件数量：1
  - 文件格式：`.pptx`
  - 解析器：`pptx`
  - 解析字符数：4012
  - chunks：13
  - 页数：13
- DeepSeek 真实端到端分析通过：
  - BP 陈述：15 条
  - 最重要看点：7 个
  - 关键假设：8 个
  - 验证任务：7 个
  - memo：2 条
  - memo 包含最重要看点：是
  - 最重要看点均带来源：是

## 本地功能覆盖

已由测试和代码路径验证：

- 项目创建
- PPTX 文档解析
- chunk 生成并保留页码来源
- LLM 配置读取
- LLM 缺失时不写入半成品分析
- BP 分析结果 schema 校验
- 最重要看点数量校验
- BP 陈述、最重要看点、关键假设、验证任务入库
- memo 基于结构化数据生成

## 仍需人工查看的部分

自动验收已经证明项目主链路可以运行，但以下内容质量仍建议在 Streamlit 页面人工抽查：

- 最重要看点是否符合投资人阅读习惯。
- 关键假设是否足够尖锐。
- 验证任务是否可执行。
- memo 是否符合用户预期的投研表达。

## 复现命令

```bash
python3 scripts/readiness_check.py --send-to-llm
```

该脚本会临时创建测试项目，执行真实 BP 分析，然后恢复原有 `data/` 和 `uploads/` 目录，不打印 BP 正文。
