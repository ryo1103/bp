# PRD：AI 辅助投研工作流工具（Python 无登录注册 MVP 版）

## 1. 产品概述

本产品是一款面向投资人的单实例 Web 工具，用 AI 帮助用户在拿到创业公司 BP 后，完成第一轮结构化投资分析，并在后续获得补充材料时，持续验证 BP 中的关键陈述和前期疑点。

第一版定位为可本地或单服务器部署的 Python Web 应用，不做登录注册、不做用户权限、不做多人协作。用户打开系统后直接进入项目列表和项目工作台，创建项目并上传 BP。

产品核心不是替投资人直接判断“投 / 不投”，而是帮助投资人把 BP 里的信息转化为一套可验证的投研工作流：

- BP 里说了什么？
- 哪些内容是最值得继续看的投资看点？
- 哪些信息是关键投资假设？
- 哪些假设目前只是公司单方面陈述？
- 后续需要什么材料、访谈或数据来验证？
- 新补充的信息是否解决了之前的问题？

产品定位：**AI 投研分析助手 + BP 假设验证系统**。

## 2. 目标用户与核心价值

目标用户：

- 个人投资人
- 天使投资人
- 小型 VC / 早期基金
- 投资经理
- 家族办公室早期项目分析人员

核心价值：

- 降低投资人阅读 BP 的分析门槛。
- 把 BP 叙事拆成可验证的陈述、看点、假设和任务。
- 自动生成后续尽调问题和材料清单。
- 帮助投资人持续跟踪疑点是否被补充材料解决。
- 让投资判断从“感觉 BP 讲得不错”变成“关键看点和关键假设是否被验证”。

## 3. 核心使用流程

### 3.1 首次拿到 BP

用户打开系统后，直接创建投资项目并上传 BP。系统完成第一轮 AI 投资分析。

系统需要识别：

- BP 中已经披露的信息
- BP 中最重要的投资看点
- BP 中的核心卖点
- BP 中的关键数据
- BP 中尚未证明的关键假设
- 需要后续验证的问题

输出结果包括：

- 公司结构化摘要
- 商业逻辑拆解
- BP 陈述清单
- 最重要看点清单
- 关键假设表
- 验证任务清单
- 尽调问题清单
- 需要补充的材料清单
- 初步投资分析 memo

### 3.2 后续补充信息验证

用户后续上传补充信息，例如财务数据、客户合同、访谈纪要、产品数据、工商资料、创始人补充说明等。

系统需要判断：

- 新材料对应 BP 中哪些陈述
- 新材料能否验证之前的关键假设
- 原有验证任务是否解决、部分解决或仍未解决
- 是否发现与 BP 不一致的信息
- 是否产生新的验证任务
- 项目整体风险判断是否变化

输出结果包括：

- 补充材料摘要
- 已验证的 BP 陈述
- 未验证或仍存疑的陈述
- 验证任务状态更新
- 新增追问
- 更新后的投资 memo

## 4. 核心概念定义

### 4.1 BP 陈述

BP 中公司明确表达的信息，例如：

- 我们服务某类客户
- 市场规模为多少
- 已有多少客户
- 收入增长多少
- 产品具备某种技术优势
- 团队有某些行业资源

系统应默认这些是“公司陈述”，而不是已经被验证的事实。

### 4.2 最重要看点

BP 中最值得投资人继续深入研究的积极信号。

每个看点包含：

- 看点标题
- 对应 BP 陈述
- 来源页码或片段位置
- 为什么重要
- 当前证据充分度
- 后续验证方向

看点不是最终投资结论，只是“值得继续看的原因”。看点必须和 BP 陈述及来源绑定，不能凭空生成。

### 4.3 关键假设

如果该假设不成立，公司商业逻辑会受到重大影响的判断。

例如：

- 客户确实有强痛点
- 客户愿意付费
- 收入可以复制增长
- 市场规模足够大
- 产品能规模化交付
- 团队具备进入该行业的关键能力
- 技术或数据壁垒真实存在

### 4.4 疑点 / 漏洞

第一版不单独设置“BP 可能漏洞”模块。疑点和漏洞由 **关键假设 + 验证任务** 共同承载：

> BP 中对公司成立至关重要，但当前证据不足、需要后续验证的关键假设，会自动转化为验证任务。

这样避免“漏洞清单”和“验证任务”重复展示。

### 4.5 验证状态

每个关键假设和验证任务都应有状态：

- 未验证：BP 有陈述，但没有充分证据。
- 部分验证：有相关证据，但还缺关键数据。
- 已验证：补充材料提供了直接、充分、可追溯证据。
- 无法验证：当前材料无法验证，需要访谈、第三方数据或专业尽调。
- 被反证：补充材料与 BP 陈述存在明显冲突。

## 5. MVP 核心功能

### 5.1 项目创建与 BP 上传

用户进入系统后直接创建投资项目并上传 BP。

支持格式：

- PDF
- PPT / PPTX
- Word / DOCX
- TXT / Markdown
- 文本粘贴
- 图片截图暂不做 OCR 自动识别，第一版提示用户粘贴 OCR 后正文

系统需要提取：

- 公司名称
- 所属行业
- 一句话介绍
- 目标客户
- 产品形态
- 解决的问题
- 商业模式
- 收入模式
- 当前客户情况
- 当前经营数据
- 团队背景
- 融资金额
- 融资用途
- BP 中出现的关键指标

所有提取内容必须标注来源页码或段落位置。

### 5.2 BP 初步分析

系统基于 BP 输出结构化分析。

必须包含：

1. **公司摘要**
   - 公司做什么
   - 卖给谁
   - 解决什么问题
   - 如何赚钱
   - 当前融资阶段

2. **BP 陈述清单**
   - BP 中的重要事实陈述
   - BP 中的重要判断陈述
   - BP 中的重要数据陈述
   - 每条陈述的来源位置

3. **最重要看点**
   - 3-7 个最值得继续看的投资看点
   - 每个看点必须绑定 BP 陈述和来源
   - 每个看点必须说明为什么重要、证据充分度和后续验证方向

4. **关键假设表**
   - 假设内容
   - BP 中的支持证据
   - 当前验证状态
   - 风险等级
   - 如果假设不成立的影响
   - 后续验证方法

5. **验证任务清单**
   - 需求验证任务
   - 市场验证任务
   - 增长验证任务
   - 商业模式验证任务
   - 团队验证任务
   - 技术 / 壁垒验证任务
   - 财务质量验证任务
   - 融资用途验证任务

6. **尽调问题清单**
   - 问创始人的问题
   - 问客户的问题
   - 需要公司补充的数据
   - 建议核验的外部资料

7. **反方投资 memo**
   - 最可能失败的原因
   - BP 中最需要验证的陈述
   - 最可能被美化的数据
   - 一票否决风险

8. **阶段性建议**
   - 继续看
   - 暂缓
   - 不建议继续
   - 等待补充信息

建议必须基于“当前证据充分度”，不能直接替用户做最终投资决策。

### 5.3 验证任务管理

系统将关键假设转化为项目级验证任务。

每个验证任务包含：

- 任务标题
- 对应 BP 陈述
- 对应关键假设
- 风险等级
- 当前验证状态
- 当前已有证据
- 缺失证据
- 建议补充材料
- 建议访谈对象
- 更新时间

用户可以：

- 编辑任务
- 删除任务
- 手动修改状态
- 添加备注

### 5.4 补充材料上传与验证

用户上传后续材料后，系统自动匹配历史验证任务。

系统需要输出：

- 本次材料新增了哪些事实
- 对应 BP 中哪些陈述
- 解决了哪些验证任务
- 哪些验证任务只是部分解决
- 哪些验证任务仍未解决
- 是否发现与 BP 不一致的信息
- 是否产生新验证任务

状态更新规则：

- 如果材料直接支持 BP 陈述，则更新为“已验证”或“部分验证”。
- 如果材料无法证明该陈述，则保持“未验证”。
- 如果材料与 BP 陈述冲突，则标记为“被反证”。
- 如果需要客户访谈或第三方数据才能判断，则标记为“无法验证”。

### 5.5 投资 memo 生成

系统支持生成阶段性投资分析报告。

报告包含：

- 项目基本信息
- BP 摘要
- 最重要看点
- BP 关键陈述
- 关键假设表
- 验证任务与状态
- 补充材料分析
- 仍需尽调的问题
- 反方观点
- 阶段性建议

第一版支持 Markdown 预览和下载。

### 5.6 第一版明确不做

- 登录注册
- 用户中心
- 用户权限
- 多租户
- 团队协作
- 多人审批流
- 外部数据库自动查询
- 自动工商信息抓取
- 自动客户访谈
- 投后管理
- CRM
- 自动估值定价
- 自动给出最终投决
- 独立 BP 可能漏洞模块

## 6. 页面设计

第一版使用 Streamlit 实现项目工作台。

### 6.1 项目列表 / 项目选择

显示：

- 公司名称
- 行业
- 当前阶段
- 最新建议
- 未验证高风险假设数量
- 已验证任务数量
- 最近更新时间

用户可以：

- 创建新项目
- 选择项目
- 删除项目

### 6.2 项目详情页

包含五个标签页：

1. **概览**
   - 公司摘要
   - 当前建议
   - 高风险未验证项
   - 最新材料状态
   - 最新分析任务状态

2. **BP 分析**
   - BP 陈述清单
   - 公司结构化信息
   - 商业逻辑拆解
   - 最重要看点
   - 关键假设表

3. **验证任务**
   - 验证任务清单
   - 验证状态
   - 风险等级
   - 缺失材料
   - 后续问题
   - 用户备注

4. **补充材料**
   - 上传材料
   - 材料摘要
   - 与历史任务的匹配结果
   - 新增追问

5. **投资 memo**
   - 生成报告
   - 预览报告
   - 下载 Markdown

## 7. AI 工作流

### 7.1 首次 BP 分析链路

输入：

- BP 文件或粘贴文本

处理：

1. 文件解析。
2. 生成文档 chunks。
3. 调用 OpenAI-compatible LLM。
4. 提取 BP 陈述。
5. 识别关键经营信息。
6. 生成最重要看点。
7. 拆解商业逻辑。
8. 生成关键假设。
9. 将关键假设转化为验证任务。
10. 生成初步 memo。

输出：

- 公司摘要
- BP 陈述清单
- 最重要看点
- 关键假设表
- 验证任务
- 初步投资 memo

### 7.2 补充材料验证链路

输入：

- 新补充材料
- 历史 BP 陈述
- 历史关键假设
- 历史验证任务

处理：

1. 解析补充材料。
2. 提取新增事实。
3. 匹配相关 BP 陈述、关键假设和验证任务。
4. 判断是否验证旧假设。
5. 更新验证任务状态。
6. 识别冲突信息。
7. 生成新的追问。
8. 生成更新后的 memo。

输出：

- 材料摘要
- 已验证陈述
- 未验证陈述
- 状态变化记录
- 新增验证任务
- 更新后的 memo

### 7.3 AI 约束

- AI 只抽取 BP 陈述，不默认判断真假。
- 每条 claim 必须引用来源 chunk。
- 每条最重要看点必须绑定 BP 陈述和来源。
- 没有来源的 claim 或看点必须丢弃。
- 每个状态变化都必须有证据来源。
- Memo 必须基于结构化数据生成。
- AI 输出必须通过 schema 校验。
- 未配置 LLM API key 时，不写入半成品分析，必须提示用户配置。
- 不允许输出确定性投资承诺语言。

## 8. 技术架构

第一版前后端均使用 Python。

```text
Streamlit App
  ↓
Python Services
  ↓
SQLite + Local Uploads
  ↓
OpenAI-compatible LLM Provider
```

### 8.1 前端

使用：

- `Streamlit`
- `pandas`

前端负责：

- 项目列表和项目选择
- 项目创建
- BP 上传
- 补充材料上传
- 分析进度和错误展示
- BP 陈述展示
- 最重要看点展示
- 关键假设表
- 验证任务管理
- 投资 memo 预览和 Markdown 下载

### 8.2 后端 / 业务层

使用 Python service modules：

- `services/storage.py`：SQLite 持久化
- `services/parser.py`：文档解析
- `services/llm.py`：OpenAI-compatible LLM 调用
- `services/pipeline.py`：BP 分析、补充材料验证、memo 生成

### 8.3 文档处理

第一版支持：

- TXT / Markdown：直接读取文本
- PDF：`pypdf`
- DOCX：`python-docx`
- PPTX：`python-pptx`
- 图片：暂不做自动 OCR，提示用户粘贴 OCR 后文本

### 8.4 AI Provider

通过环境变量配置：

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

要求兼容 OpenAI Chat Completions API。

## 9. 数据模型

### projects

```text
id
company_name
industry
financing_stage
one_liner
current_recommendation
risk_level
created_at
updated_at
```

### documents

```text
id
project_id
document_type: bp | supplementary
file_name
file_path
parse_status: pending | completed | failed
summary
created_at
updated_at
```

### document_chunks

```text
id
document_id
project_id
chunk_index
page_number
section_label
text
created_at
```

### bp_claims

```text
id
project_id
document_id
claim_text
claim_type: fact | judgment | data
topic
source_chunk_id
source_page
source_quote
verification_status
created_at
updated_at
```

### key_highlights

```text
id
project_id
document_id
title
linked_claim_text
source_chunk_id
source_page
why_important
evidence_level
verification_direction
created_at
updated_at
```

### investment_assumptions

```text
id
project_id
assumption_text
importance: high | medium | low
risk_level: high | medium | low
current_status
why_it_matters
failure_impact
verification_method
created_at
updated_at
```

### verification_tasks

```text
id
project_id
title
task_type
linked_claim_id
linked_assumption_id
risk_level
status
existing_evidence
missing_evidence
suggested_materials
suggested_interviewees
founder_questions
customer_questions
user_notes
created_at
updated_at
```

### evidence_links

```text
id
project_id
task_id
claim_id
document_id
chunk_id
evidence_text
judgment: supports | partially_supports | contradicts | irrelevant
confidence
created_at
```

### investment_memos

```text
id
project_id
memo_type: initial | updated
content_markdown
source_snapshot_json
created_at
updated_at
```

## 10. 迭代计划

### Milestone 1：Python 工程骨架

完成：

- Streamlit 应用
- SQLite schema
- 本地文件上传目录
- 项目 CRUD
- 基础页面结构

验收：

- 用户可启动应用。
- 用户可创建、选择、删除项目。
- 数据可写入 SQLite。

### Milestone 2：文档上传与解析

完成：

- TXT / Markdown / PDF / DOCX / PPTX 解析
- document_chunks 入库
- 解析状态展示

验收：

- 上传 BP 后可看到解析文本和来源位置。
- 解析失败时用户能看到错误状态。

### Milestone 3：首次 AI 分析

完成：

- LLMClient
- BP 陈述提取
- 最重要看点生成
- 关键假设生成
- 验证任务生成
- initial memo

验收：

- 上传 BP 后自动生成 claims。
- 自动生成 3-7 个最重要看点。
- 自动生成至少 5 个关键假设。
- 自动生成至少 5 个验证任务。
- 所有 claims 和 highlights 必须绑定来源。

### Milestone 4：验证任务管理

完成：

- 验证任务列表
- 状态筛选
- 风险筛选
- 用户手动编辑任务
- 用户备注

验收：

- 用户可修改任务状态和备注。
- 修改后项目概览统计同步更新。

### Milestone 5：补充材料验证

完成：

- 补充材料上传
- AI 匹配历史任务
- evidence_links 入库
- 自动更新 task 状态

验收：

- 上传补充材料后，系统能关联历史验证任务。
- 每个状态变化都能看到证据来源。
- 冲突材料会标记为 contradicted。

### Milestone 6：投资 Memo

完成：

- 从结构化数据生成 memo
- memo 存档
- Markdown 预览
- Markdown 下载

验收：

- memo 包含项目摘要、最重要看点、关键陈述、假设、验证任务状态、反方观点、阶段性建议。
- memo 不重新凭空分析，必须基于结构化数据。

## 11. 测试计划

### PRD 检查

- 不再把“BP 可能漏洞”作为独立模块。
- 明确漏洞 / 疑点由关键假设和验证任务表达。
- 明确第一版前后端都用 Python。
- 明确 BP 分析必须生成“最重要看点”。

### 功能测试

- 创建项目。
- 上传 BP。
- AI 生成 BP 陈述、最重要看点、关键假设、验证任务。
- 上传补充材料。
- 自动匹配历史验证任务并更新状态。
- 手动修改任务状态和备注。
- 生成 Markdown memo。

### AI 测试

- LLM 返回合法 JSON 时正常入库。
- LLM 返回非法 JSON 时显示失败原因。
- 未配置 API key 时提示配置，不写入半成品分析。

### 文档测试

- TXT、PDF、DOCX、PPTX 各至少一个样例。
- 所有 BP 陈述和看点必须带来源页码或片段引用。

## 12. 成功指标

- BP 上传后 3 分钟内生成完整初步分析。
- 每个项目生成 3-7 个最重要看点。
- 每个项目至少生成 5 个有效关键假设。
- 每个项目至少生成 5 个可执行验证任务。
- 用户手动保留 AI 生成验证任务的比例高于 60%。
- 补充材料上传后，系统能正确匹配至少 70% 的相关历史任务。
- 用户能基于系统输出明确下一步要问创始人什么、要什么材料。

## 13. 风险与约束

主要风险：

- AI 把 BP 陈述误认为已验证事实。
- AI 把“看点”写成确定性投资结论。
- AI 对早期公司过度推断。
- BP 文件质量差导致解析错误。
- 补充材料无法直接证明验证任务。
- 用户误把 AI 阶段性建议当作最终投资意见。

产品约束：

- 必须区分“BP 陈述”和“已验证事实”。
- 必须标注信息来源。
- 最重要看点必须绑定来源。
- 必须允许用户人工修改 AI 结果。
- 必须避免确定性投资承诺语言。
- 必须把输出重点放在验证路径，而不是单点结论。
- 第一版数据为实例级数据，不做用户隔离。

## 14. 后续版本方向

- 登录注册
- 多用户账号体系
- 多租户数据隔离
- 团队协作
- 权限管理
- 外部工商 / 新闻 / 投融资数据库查询
- 图片 OCR
- PDF / Word 导出
- 客户访谈记录管理
- 更完整的投研工作流和项目看板
