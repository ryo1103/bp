from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .llm import LLMClient
from .models import LLMResponseError
from .parser import parse_document
from .research_provider import NullResearchProvider, ResearchProvider
from .storage import (
    create_ai_suggestion,
    create_material_request,
    create_strategy_match,
    get_project_bundle,
    insert_memo,
    insert_supplementary_verification,
    new_id,
    replace_bp_analysis,
    save_uploaded_file,
    upsert_memo_sections,
)


VALID_STATUSES = {"unverified", "partially_verified", "verified", "unverifiable", "contradicted"}
VALID_RISKS = {"high", "medium", "low"}
VALID_RED_FLAG_STATUSES = {"open", "partially_resolved", "resolved", "contradicted"}
VALID_RED_FLAG_TYPES = {"team", "customer", "revenue", "qualification", "financing", "technology", "logic", "other"}
FORBIDDEN_AI_DECISION_PHRASES = [
    "建议投资",
    "建议放弃",
    "值得投",
    "不值得投",
    "可投",
    "不可投",
    "投资价值较高",
    "可投性较高",
    "尽调通过",
    "不建议继续推进",
    "该项目不适合继续看",
]


FINANCIAL_KEYWORDS = ["收入", "营收", "毛利", "利润", "现金流", "回款", "应收", "财务", "成本", "费用", "资产负债", "损益"]


def _chunks_for_prompt(chunks: List[Dict[str, Any]], limit: int = 25) -> str:
    rows = []
    for chunk in chunks[:limit]:
        file_name = chunk.get("file_name") or chunk.get("document_name") or ""
        file_prefix = f" file={file_name}" if file_name else ""
        rows.append(
            f"[chunk_id={chunk['id']}{file_prefix} page={chunk['page_number']} section={chunk['section_label']}]\n{chunk['text']}"
        )
    return "\n\n".join(rows)


def _looks_like_financial_material(file_name: str, text: str) -> bool:
    lowered_name = file_name.lower()
    if lowered_name.endswith((".csv", ".xlsx")):
        return True
    sample = text[:6000]
    return sum(1 for keyword in FINANCIAL_KEYWORDS if keyword in sample) >= 2


def _assert_keys(payload: Dict[str, Any], keys: List[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise LLMResponseError(f"{label} 缺少字段：{', '.join(missing)}")


def validate_low_authority_ai_output(payload: Dict[str, Any]) -> List[str]:
    text = json.dumps(payload, ensure_ascii=False)
    errors = [f"AI 输出包含禁用决策文案：{phrase}" for phrase in FORBIDDEN_AI_DECISION_PHRASES if phrase in text]
    if "investment_score" in payload:
        errors.append("AI 输出不得包含 investment_score")
    if "recommendation" in payload:
        errors.append("AI 输出不得包含 recommendation")
    if "reject_reason_by_ai" in payload:
        errors.append("AI 输出不得包含 reject_reason_by_ai")
    for flag in payload.get("red_flags", []):
        if flag.get("status") in {"human_confirmed_risk", "confirmed"}:
            errors.append("AI 不得确认风险，只能生成待核验风险或疑似异常")
    for risk in payload.get("risk_items", []):
        if risk.get("risk_status") == "human_confirmed_risk":
            errors.append("AI 不得生成 human_confirmed_risk")
    for action in payload.get("suggested_actions", []):
        if action.get("action_status") and action.get("action_status") != "ai_suggested":
            errors.append("AI 建议动作初始状态必须为 ai_suggested")
    return errors


def _normalize_source_fields(item: Dict[str, Any], chunk_map: Dict[str, Dict[str, Any]]) -> None:
    if "source_chunk_id" not in item:
        item["source_chunk_id"] = item.get("chunk_id") or item.get("source_id") or item.get("source") or ""
    if "source_quote" not in item:
        item["source_quote"] = item.get("quote") or item.get("evidence") or item.get("linked_claim_text") or item.get("claim_text") or ""
    if "source_page" not in item and item.get("source_chunk_id") in chunk_map:
        item["source_page"] = int(chunk_map[item["source_chunk_id"]]["page_number"])


def validate_bp_analysis(payload: Dict[str, Any], chunk_ids: set[str], chunk_map: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    chunk_map = chunk_map or {}
    _assert_keys(
        payload,
        [
            "company_summary",
            "document_summary",
            "bp_claims",
            "key_highlights",
            "assumptions",
            "verification_tasks",
            "sector_analysis",
            "industry_map",
            "industry_terms",
            "red_flags",
            "funding_analysis",
            "stage_recommendation",
            "risk_level",
            "initial_memo",
        ],
        "BP 分析结果",
    )
    if payload["risk_level"] not in VALID_RISKS:
        payload["risk_level"] = "medium"

    for claim in payload["bp_claims"]:
        _normalize_source_fields(claim, chunk_map)
        _assert_keys(claim, ["claim_text", "claim_type", "topic", "source_chunk_id", "source_page", "source_quote"], "BP 陈述")
        if claim["source_chunk_id"] not in chunk_ids:
            raise LLMResponseError("BP 陈述引用了不存在的 chunk")

    for highlight in payload["key_highlights"]:
        _normalize_source_fields(highlight, chunk_map)
        _assert_keys(
            highlight,
            [
                "title",
                "linked_claim_text",
                "source_chunk_id",
                "source_page",
                "why_important",
                "evidence_level",
                "verification_direction",
            ],
            "最重要看点",
        )
        if highlight["source_chunk_id"] not in chunk_ids:
            raise LLMResponseError("最重要看点引用了不存在的 chunk")

    for assumption in payload["assumptions"]:
        _assert_keys(
            assumption,
            [
                "assumption_text",
                "importance",
                "risk_level",
                "why_it_matters",
                "failure_impact",
                "verification_method",
            ],
            "关键假设",
        )
        if assumption["risk_level"] not in VALID_RISKS:
            assumption["risk_level"] = "medium"

    for task in payload["verification_tasks"]:
        _assert_keys(
            task,
            [
                "title",
                "task_type",
                "risk_level",
                "existing_evidence",
                "missing_evidence",
                "suggested_materials",
                "suggested_interviewees",
                "founder_questions",
                "customer_questions",
            ],
            "验证任务",
        )
        if task["risk_level"] not in VALID_RISKS:
            task["risk_level"] = "medium"

    _assert_keys(
        payload["sector_analysis"],
        [
            "primary_industry",
            "sub_sector",
            "target_customer",
            "value_chain_position",
            "replacement_target",
            "profit_pool_logic",
            "summary",
        ],
        "赛道分析",
    )

    for node in payload["industry_map"]:
        _assert_keys(node, ["node_type", "label", "description", "is_company_position"], "产业图节点")
        node["is_company_position"] = bool(node["is_company_position"])

    for term in payload["industry_terms"]:
        _assert_keys(term, ["term", "explanation", "relevance"], "行业关键词")

    for flag in payload["red_flags"]:
        _normalize_source_fields(flag, chunk_map)
        _assert_keys(
            flag,
            [
                "title",
                "flag_type",
                "severity",
                "status",
                "evidence",
                "source_chunk_id",
                "source_page",
                "why_it_matters",
                "suggested_verification",
            ],
            "直接异常",
        )
        if flag["flag_type"] not in VALID_RED_FLAG_TYPES:
            flag["flag_type"] = "other"
        if flag["severity"] not in VALID_RISKS:
            flag["severity"] = "medium"
        if flag["status"] not in VALID_RED_FLAG_STATUSES:
            flag["status"] = "open"
        if flag["source_chunk_id"] and flag["source_chunk_id"] not in chunk_ids:
            raise LLMResponseError("直接异常引用了不存在的 chunk")

    _assert_keys(
        payload["funding_analysis"],
        [
            "stated_round",
            "inferred_round",
            "round_confidence",
            "material_sufficiency",
            "risk_return_profile",
            "stability_assessment",
            "payback_cycle_view",
            "investor_signal",
            "existing_investors",
            "missing_round_evidence",
            "valuation_fit",
            "suggested_checks",
        ],
        "融资轮次分析",
    )
    if payload["funding_analysis"]["round_confidence"] not in VALID_RISKS:
        payload["funding_analysis"]["round_confidence"] = "medium"
    if not isinstance(payload["funding_analysis"]["existing_investors"], list):
        payload["funding_analysis"]["existing_investors"] = []

    if not (3 <= len(payload["key_highlights"]) <= 7):
        raise LLMResponseError("最重要看点数量必须为 3-7 个")
    if len(payload["assumptions"]) < 5:
        raise LLMResponseError("关键假设至少需要 5 个")
    if len(payload["verification_tasks"]) < 5:
        raise LLMResponseError("验证任务至少需要 5 个")
    return payload


def validate_supplementary(payload: Dict[str, Any], task_ids: set[str], chunk_ids: set[str]) -> Dict[str, Any]:
    _assert_keys(payload, ["material_summary", "task_updates", "stage_recommendation", "risk_level", "updated_memo"], "补充材料验证结果")
    payload.setdefault("red_flag_updates", [])
    payload.setdefault("material_resolutions", [])
    payload.setdefault("financial_analysis", {})
    if payload["risk_level"] not in VALID_RISKS:
        payload["risk_level"] = "medium"
    for update in payload["task_updates"]:
        _assert_keys(update, ["task_id", "new_status", "chunk_id", "evidence_text", "judgment", "confidence"], "任务状态更新")
        if update["task_id"] not in task_ids:
            raise LLMResponseError("补充材料验证引用了不存在的 task")
        if update["chunk_id"] not in chunk_ids:
            raise LLMResponseError("补充材料验证引用了不存在的 chunk")
        if update["new_status"] not in VALID_STATUSES:
            update["new_status"] = "unverifiable"
    for update in payload["red_flag_updates"]:
        _assert_keys(update, ["red_flag_id", "new_status", "evidence_text", "impact_summary", "remaining_gap", "resolution_note"], "红旗状态更新")
        if update["new_status"] not in VALID_RED_FLAG_STATUSES:
            update["new_status"] = "open"
    for resolution in payload["material_resolutions"]:
        _assert_keys(
            resolution,
            ["target_type", "target_id", "target_title", "resolution_status", "evidence_text", "impact_summary", "remaining_gap"],
            "补充材料解决问题汇总",
        )
    return payload


def _bp_analysis_messages(chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是投研验证助手，不是投资决策者。只基于给定 BP chunks 输出 JSON。"
                "必须区分 BP 陈述、AI 推断和已验证事实；不得给最终投资承诺。"
                "禁止输出“建议投资”“建议放弃”“值得投”“不值得投”“可投性”等表述。"
                "如材料不足，必须明确写“当前材料不足以判断”，不得补全事实。"
                "风险只能标记为待核验或疑似异常，不能标记为确认风险。"
            ),
        },
        {
            "role": "user",
            "content": f"""
请综合分析以下 BP chunks，并返回严格 JSON。chunks 可能来自多个 BP 文件、更新版 BP 或用户粘贴正文；请做一次合并后的项目级分析，不要按文件分别输出。

{{
  "company_summary": {{"company_name": "", "industry": "", "financing_stage": "", "one_liner": ""}},
  "document_summary": "",
  "bp_claims": [
    {{"claim_text": "", "claim_type": "fact|judgment|data", "topic": "", "source_chunk_id": "", "source_page": 1, "source_quote": ""}}
  ],
  "key_highlights": [
    {{"title": "", "linked_claim_text": "", "source_chunk_id": "", "source_page": 1, "why_important": "", "evidence_level": "低|中|高", "verification_direction": ""}}
  ],
  "assumptions": [
    {{"assumption_text": "", "importance": "high|medium|low", "risk_level": "high|medium|low", "why_it_matters": "", "failure_impact": "", "verification_method": ""}}
  ],
  "verification_tasks": [
    {{"title": "", "task_type": "demand|market|growth|business_model|team|moat|financial_quality|financing_use", "risk_level": "high|medium|low", "existing_evidence": "", "missing_evidence": "", "suggested_materials": "", "suggested_interviewees": "", "founder_questions": "", "customer_questions": ""}}
  ],
  "sector_analysis": {{"primary_industry": "", "sub_sector": "", "target_customer": "", "value_chain_position": "", "replacement_target": "", "profit_pool_logic": "", "summary": ""}},
  "industry_map": [
    {{"node_type": "upstream|midstream|downstream|service|customer|regulator|company", "label": "", "description": "", "is_company_position": false}}
  ],
  "industry_terms": [
    {{"term": "", "explanation": "", "relevance": ""}}
  ],
  "red_flags": [
    {{"title": "", "flag_type": "team|customer|revenue|qualification|financing|technology|logic|other", "severity": "high|medium|low", "status": "open", "evidence": "", "source_chunk_id": "", "source_page": 1, "why_it_matters": "", "suggested_verification": ""}}
  ],
  "funding_analysis": {{"stated_round": "", "inferred_round": "", "round_confidence": "high|medium|low", "material_sufficiency": "", "risk_return_profile": "", "stability_assessment": "", "payback_cycle_view": "", "investor_signal": "", "existing_investors": [{{"name": "", "investor_type": "institution|corporate|government|individual|unknown", "round": "", "signal_strength": "high|medium|low", "why_it_matters": "", "needs_verification": ""}}], "missing_round_evidence": "", "valuation_fit": "", "suggested_checks": ""}},
  "stage_recommendation": "当前材料显示出继续研究信号|当前材料不足以支持进一步判断|存在待核验信息缺口|待补充材料后再判断",
  "risk_level": "high|medium|low",
  "initial_memo": ""
}}

要求：
- key_highlights 必须 3-7 个，且每条绑定 source_chunk_id。
- assumptions 至少 5 个。
- verification_tasks 至少 5 个。
- sector_analysis 要把 BP 的宽泛说法翻译成可投资的细分赛道，并说明公司在价值链中的位置。
- industry_map 至少 5 个节点，必须包含一个 is_company_position=true 的公司位置节点。
- industry_terms 输出 5-12 个行业关键词，解释要让第一次接触该行业的投资人能理解。
- red_flags 只写“一开始就不符合逻辑或真实性风险明显”的问题，例如人员履历冲突、客户/收入/资质/融资/技术指标前后矛盾、明显夸大。不要把普通信息缺失写入 red_flags，普通信息缺失放入 assumptions 和 verification_tasks。
- funding_analysis 必须判断 BP 声称轮次和材料反推出的轮次是否匹配；说明该轮次下资料充分度是否合理、风险收益特征、稳定性、回款周期/现金流预期、估值匹配度，以及已有投资人对项目可信度的信号。越早期应强调高不确定性和高上行，越后期应强调稳定性、利润率/增长空间、回款周期和可验证财务表现。
- existing_investors 要抽取 BP 中出现的历史投资人、领投方、跟投方、产业方或政府基金；没有披露则返回空数组，并在 investor_signal 和 missing_round_evidence 说明缺口。
- bp_claims 和 key_highlights 的 source_chunk_id 必须从下方 chunks 的 chunk_id 中选择。
- bp_claims、key_highlights、red_flags 必须填写 source_page；source_page 必须等于对应 chunk 的 page。若没有直接异常，red_flags 返回空数组。
- 不允许省略上方 JSON 示例中的任何字段。
- 不要输出独立“可能漏洞”模块；疑点由 assumptions 和 verification_tasks 表达。
- 禁止输出投资建议、放弃建议、可投性、投资价值分或尽调通过等决策类表达。

BP chunks:
{_chunks_for_prompt(chunks)}
""",
        },
    ]


def analyze_bp_batch(
    project_id: str,
    uploads: List[Dict[str, Any]],
    pasted_text: str,
    include_existing: bool = True,
    llm: LLMClient | None = None,
    research_provider: ResearchProvider | None = None,
) -> Dict[str, Any]:
    llm = llm or LLMClient()
    research_provider = research_provider or NullResearchProvider()
    pasted_text = pasted_text.strip()
    bundle = get_project_bundle(project_id)
    bp_documents = {document["id"]: document for document in bundle["documents"] if document["document_type"] == "bp"}
    existing_chunks: List[Dict[str, Any]] = []
    if include_existing:
        for chunk in bundle["chunks"]:
            if chunk["document_id"] in bp_documents:
                document = bp_documents[chunk["document_id"]]
                existing_chunks.append({**chunk, "file_name": document["file_name"]})

    new_documents: List[Dict[str, Any]] = []
    new_chunks: List[Dict[str, Any]] = []

    for upload in uploads:
        name = upload.get("name") or "uploaded-bp.txt"
        content = upload.get("content") or b""
        if not content:
            continue
        path = save_uploaded_file(project_id, name, content)
        parsed = parse_document(path, "")
        if not parsed.text.strip():
            continue
        document = {
            "id": new_id("doc"),
            "document_type": "bp",
            "file_name": name,
            "file_path": str(path),
            "parser": parsed.parser,
        }
        new_documents.append(document)
        for chunk in parsed.chunks:
            new_chunks.append({**chunk, "document_id": document["id"], "file_name": name})

    if pasted_text:
        path = Path("pasted-bp.txt")
        parsed = parse_document(path, pasted_text)
        document = {
            "id": new_id("doc"),
            "document_type": "bp",
            "file_name": "粘贴 BP 正文",
            "file_path": str(path),
            "parser": parsed.parser,
        }
        new_documents.append(document)
        for chunk in parsed.chunks:
            new_chunks.append({**chunk, "document_id": document["id"], "file_name": "粘贴 BP 正文"})

    analysis_chunks = existing_chunks + new_chunks
    if not analysis_chunks:
        raise LLMResponseError("BP 解析后没有可分析文本")

    chunk_ids = {str(chunk["id"]) for chunk in analysis_chunks}
    messages = _bp_analysis_messages(analysis_chunks)
    chunk_map = {str(chunk["id"]): chunk for chunk in analysis_chunks}
    payload = validate_bp_analysis(llm.chat_json(messages), chunk_ids, chunk_map)
    errors = validate_low_authority_ai_output(payload)
    if errors:
        raise LLMResponseError("AI 输出未通过低权限校验：" + "；".join(errors))
    payload["research_context"] = research_provider.find_sector_context(
        payload["company_summary"],
        [term.get("term", "") for term in payload.get("industry_terms", [])],
    )
    replace_bp_analysis(project_id, new_documents, new_chunks, analysis_chunks, payload)
    insert_memo(
        project_id,
        payload["initial_memo"],
        {
            "type": "initial",
            "claim_count": len(payload["bp_claims"]),
            "highlight_count": len(payload["key_highlights"]),
            "assumption_count": len(payload["assumptions"]),
            "task_count": len(payload["verification_tasks"]),
        },
    )
    return payload


def analyze_bp(project_id: str, uploaded_name: str, content: bytes, pasted_text: str, llm: LLMClient | None = None) -> Dict[str, Any]:
    uploads = [{"name": uploaded_name or "pasted-bp.txt", "content": content}] if content else []
    return analyze_bp_batch(project_id, uploads, pasted_text, include_existing=False, llm=llm)


def verify_supplementary(project_id: str, uploaded_name: str, content: bytes, pasted_text: str, llm: LLMClient | None = None) -> Dict[str, Any]:
    llm = llm or LLMClient()
    bundle = get_project_bundle(project_id)
    path = save_uploaded_file(project_id, uploaded_name, content) if content else Path(uploaded_name or "pasted.txt")
    parsed = parse_document(path, pasted_text)
    if not parsed.text.strip():
        raise LLMResponseError("补充材料解析后没有可分析文本")
    document = {
        "id": new_id("doc"),
        "document_type": "supplementary",
        "file_name": uploaded_name or "粘贴补充材料",
        "file_path": str(path),
        "parser": parsed.parser,
    }
    task_ids = {task["id"] for task in bundle["tasks"]}
    chunk_ids = {str(chunk["id"]) for chunk in parsed.chunks}
    is_financial_material = _looks_like_financial_material(uploaded_name or "", parsed.text)
    history = {
        "claims": bundle["claims"],
        "assumptions": bundle["assumptions"],
        "tasks": bundle["tasks"],
        "red_flags": bundle.get("red_flags", []),
        "sector_analyses": bundle.get("sector_analyses", []),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是投研尽调验证助手。只基于补充材料和历史任务输出 JSON，不要自由发挥。"
                "你不能替研究员确认风险、关闭任务、改变人工项目状态或输出投资/放弃建议。"
                "补充材料支持状态变化时，只生成待人工确认的建议。"
            ),
        },
        {
            "role": "user",
            "content": f"""
请判断补充材料如何影响历史验证任务，返回严格 JSON：

{{
  "material_summary": "",
  "task_updates": [
    {{"task_id": "", "new_status": "unverified|partially_verified|verified|unverifiable|contradicted", "chunk_id": "", "evidence_text": "", "judgment": "supports|partially_supports|contradicts|irrelevant", "confidence": 0.0, "still_missing": "", "new_questions": ""}}
  ],
  "red_flag_updates": [
    {{"red_flag_id": "", "new_status": "open|partially_resolved|resolved|contradicted", "evidence_text": "", "impact_summary": "", "remaining_gap": "", "resolution_note": ""}}
  ],
  "material_resolutions": [
    {{"target_type": "task|red_flag|claim|assumption|financial|material", "target_id": "", "target_title": "", "resolution_status": "resolved|partially_resolved|contradicted|new_information|irrelevant", "evidence_text": "", "impact_summary": "", "remaining_gap": ""}}
  ],
  "financial_analysis": {{"summary": "", "revenue_quality": "", "margin_costs": "", "cashflow_quality": "", "customer_concentration": "", "anomalies": "", "bp_conflicts": "", "follow_up_materials": ""}},
  "stage_recommendation": "当前材料显示出继续研究信号|当前材料不足以支持进一步判断|存在待核验信息缺口|待补充材料后再判断",
  "risk_level": "high|medium|low",
  "updated_memo": ""
}}

要求：
- task_updates 只包含补充材料确实支持、部分支持、反证或改变状态的任务；无关任务不要输出。
- red_flag_updates 只包含补充材料能解释、部分解释、反证或加重的直接异常。
- material_resolutions 必须总结“补充材料解决了什么问题”或“新增信息对分析有什么用”；即使没有解决历史问题，也要输出至少 1 条 new_information 或 irrelevant。
- financial_analysis 仅当材料是财务报表、收入明细、回款、成本费用、现金流等财务材料时填写；否则所有字段留空。
- 当前材料是否像财务材料：{"是" if is_financial_material else "否"}。

历史结构化数据：
{json.dumps(history, ensure_ascii=False)[:12000]}

补充材料 chunks:
{_chunks_for_prompt(parsed.chunks)}
""",
        },
    ]
    payload = validate_supplementary(llm.chat_json(messages), task_ids, chunk_ids)
    errors = validate_low_authority_ai_output(payload)
    if errors:
        raise LLMResponseError("AI 输出未通过低权限校验：" + "；".join(errors))
    insert_supplementary_verification(project_id, document, parsed.chunks, payload)
    for update in payload.get("task_updates", []):
        create_ai_suggestion(
            project_id,
            "action_status_update",
            "verification_task",
            update.get("task_id", ""),
            update,
            "补充材料可能改变尽调动作/验证任务状态，需研究员确认。",
        )
    for update in payload.get("red_flag_updates", []):
        create_ai_suggestion(
            project_id,
            "risk_status_update",
            "red_flag",
            update.get("red_flag_id", ""),
            update,
            "补充材料可能解释或反证待核验风险，需研究员确认。",
        )
    insert_memo(
        project_id,
        payload["updated_memo"],
        {
            "type": "updated",
            "task_update_count": len(payload["task_updates"]),
        },
    )
    return payload


def build_report_from_bundle(bundle: Dict[str, Any]) -> str:
    project = bundle["project"]
    sector = bundle.get("sector_analyses", [{}])[-1] if bundle.get("sector_analyses") else {}
    funding = bundle.get("funding_analyses", [{}])[-1] if bundle.get("funding_analyses") else {}
    lines = [
        f"# {project['company_name']} 初读摘要 / Memo 草稿",
        "",
        "## 项目基本信息",
        "",
        f"- 行业：{project['industry']}",
        f"- 融资阶段：{project['financing_stage']}",
        f"- 一句话介绍：{project['one_liner']}",
        f"- AI 研究状态：{project.get('ai_research_state', 'material_insufficient')}",
        f"- 人工项目状态：{project.get('human_project_status', 'inbox')}",
        f"- 当前材料下的研究提示：{project['current_recommendation']}",
        "",
        "## 赛道归类与产业位置",
        "",
        f"- 一级行业：{sector.get('primary_industry', '待识别')}",
        f"- 细分赛道：{sector.get('sub_sector', '待识别')}",
        f"- 目标客户：{sector.get('target_customer', '待确认')}",
        f"- 价值链位置：{sector.get('value_chain_position', '待确认')}",
        f"- 替代对象：{sector.get('replacement_target', '待确认')}",
        f"- 利润池判断：{sector.get('profit_pool_logic', '待确认')}",
        "",
        sector.get("summary", "暂无行业定位摘要。"),
        "",
        "## 融资轮次与投资人信号",
        "",
        f"- BP 声称轮次：{funding.get('stated_round', project.get('financing_stage', '待确认'))}",
        f"- 反推轮次：{funding.get('inferred_round', '待确认')}",
        f"- 轮次判断置信度：{funding.get('round_confidence', 'medium')}",
        f"- 材料充分度：{funding.get('material_sufficiency', '待确认')}",
        f"- 风险收益特征：{funding.get('risk_return_profile', '待确认')}",
        f"- 稳定性判断：{funding.get('stability_assessment', '待确认')}",
        f"- 回款周期判断：{funding.get('payback_cycle_view', '待确认')}",
        f"- 投资人信号：{funding.get('investor_signal', '待确认')}",
        f"- 估值/阶段匹配：{funding.get('valuation_fit', '待确认')}",
        f"- 仍需核验：{funding.get('missing_round_evidence', '待确认')}",
        "",
        "## 产业图摘要",
        "",
    ]
    try:
        investors = json.loads(funding.get("existing_investors", "[]")) if funding else []
    except json.JSONDecodeError:
        investors = []
    if investors:
        lines.extend(["### 已披露投资人", ""])
        lines.extend(
            f"- {investor.get('name', '未知投资人')}｜{investor.get('investor_type', 'unknown')}｜轮次：{investor.get('round', '待确认')}｜信号：{investor.get('signal_strength', 'medium')}｜{investor.get('why_it_matters', '')}"
            for investor in investors
        )
        lines.append("")
    if bundle.get("industry_map_nodes"):
        lines.extend(
            f"- {node['node_type']}｜{node['label']}：{node['description']}{'（公司位置）' if node['is_company_position'] else ''}"
            for node in bundle["industry_map_nodes"]
        )
    else:
        lines.append("- 暂无。")
    lines.extend(
        [
            "",
            "## BP 中的积极信号",
            "",
        ]
    )
    lines.extend(
        f"- {item['title']}：{item['why_important']}（证据充分度：{item['evidence_level']}，来源 p{item['source_page']}）"
        for item in bundle["highlights"]
    )
    if not bundle["highlights"]:
        lines.append("- 暂无。")
    lines.extend(["", "## BP 关键陈述", ""])
    lines.extend(f"- {claim['claim_text']}（状态：{claim['verification_status']}，来源 p{claim['source_page']}）" for claim in bundle["claims"])
    if not bundle["claims"]:
        lines.append("- 暂无。")
    lines.extend(["", "## 疑似异常与待核验风险", ""])
    if bundle.get("red_flags"):
        lines.extend(
            f"- {flag['title']}｜严重度：{flag['severity']}｜状态：{flag['status']}｜依据：{flag['evidence']}｜影响：{flag['why_it_matters']}"
            for flag in bundle["red_flags"]
        )
    else:
        lines.append("- 未发现需要直接列出的明显逻辑或真实性异常。")
    lines.extend(["", "## 关键假设与尽调动作", ""])
    for task in bundle["tasks"]:
        lines.append(
            f"- {task['title']}｜风险：{task['risk_level']}｜状态：{task['status']}｜缺失证据：{task['missing_evidence']}"
        )
    if not bundle["tasks"]:
        lines.append("- 暂无。")
    lines.extend(["", "## 补充材料解决问题汇总", ""])
    if bundle.get("supplementary_resolutions"):
        lines.extend(
            f"- {item['target_title'] or item['target_type']}｜状态：{item['resolution_status']}｜影响：{item['impact_summary']}｜仍缺：{item['remaining_gap']}"
            for item in bundle["supplementary_resolutions"]
        )
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 财务与商业化核验", ""])
    if bundle.get("financial_analyses"):
        for financial in bundle["financial_analyses"]:
            lines.extend(
                [
                    f"- 摘要：{financial['summary']}",
                    f"- 收入质量：{financial['revenue_quality']}",
                    f"- 毛利/成本费用：{financial['margin_costs']}",
                    f"- 现金流/回款：{financial['cashflow_quality']}",
                    f"- 客户集中：{financial['customer_concentration']}",
                    f"- 异常波动：{financial['anomalies']}",
                    f"- 与 BP 冲突：{financial['bp_conflicts']}",
                    f"- 需补充材料：{financial['follow_up_materials']}",
                ]
            )
    else:
        lines.append("- 暂无财务材料分析。")
    lines.extend(
        [
            "",
            "## 尚未验证事项与人工讨论问题",
            "",
            "本 memo 为草稿，仅反映当前材料的可判断程度，不构成投资建议或投委会结论。",
            "",
            f"当前材料下的研究提示：{project['current_recommendation']}。",
        ]
    )
    return "\n".join(lines)


def generate_memo_from_data(project_id: str) -> str:
    bundle = get_project_bundle(project_id)
    content = build_report_from_bundle(bundle)
    memo_id = insert_memo(project_id, content, {"type": "manual_from_structured_data"})
    upsert_memo_sections(project_id, memo_id, build_memo_sections(bundle))
    return content


def build_memo_sections(bundle: Dict[str, Any]) -> List[Dict[str, str]]:
    project = bundle["project"]
    return [
        {"section_key": "project_description", "section_title": "一句话项目描述", "ai_draft": project["one_liner"]},
        {"section_key": "material_scope", "section_title": "当前材料范围", "ai_draft": f"已上传材料 {len(bundle['documents'])} 份，材料阶段：{project.get('material_stage', 'only_bp')}。"},
        {"section_key": "readiness", "section_title": "当前可判断程度", "ai_draft": f"当前可判断程度：{project.get('judgement_readiness', 'very_limited')}；AI 研究状态：{project.get('ai_research_state', 'material_insufficient')}。"},
        {"section_key": "company_claims", "section_title": "材料陈述（未核验）", "ai_draft": "\n".join(f"- {claim['claim_text']}" for claim in bundle["claims"])},
        {"section_key": "hypotheses", "section_title": "核心待验证假设", "ai_draft": "\n".join(f"- {item['assumption_text']}" for item in bundle["assumptions"])},
        {"section_key": "risks", "section_title": "待核验风险", "ai_draft": "\n".join(f"- {flag['title']}：{flag['why_it_matters']}" for flag in bundle.get("red_flags", []))},
        {"section_key": "actions", "section_title": "下一步验证动作", "ai_draft": "\n".join(f"- {task['title']}：{task['missing_evidence']}" for task in bundle["tasks"])},
        {"section_key": "discussion", "section_title": "供研究员讨论的问题", "ai_draft": "当前 memo 为草稿，需研究员结合补充材料、访谈和外部核验后形成正式判断。"},
    ]


def analyze_strategy_match(project_id: str, strategy_id: str) -> Dict[str, Any]:
    bundle = get_project_bundle(project_id)
    strategy = next((item for item in bundle.get("fund_strategies", []) if item["id"] == strategy_id), None)
    if not strategy:
        raise LLMResponseError("基金策略不存在")
    project = bundle["project"]
    matched: list[str] = []
    unknown: list[str] = []
    outside: list[str] = []

    focus = strategy.get("focus_sectors") or ""
    excluded = strategy.get("excluded_sectors") or ""
    preferred_stages = strategy.get("preferred_stages") or ""
    excluded_stages = strategy.get("excluded_stages") or ""
    if focus and project["industry"] and project["industry"] in focus:
        matched.append("行业在关注赛道描述中出现")
    elif excluded and project["industry"] and project["industry"] in excluded:
        outside.append("行业出现在排除赛道描述中")
    else:
        unknown.append("行业匹配需要进一步确认")
    if preferred_stages and project["financing_stage"] and project["financing_stage"] in preferred_stages:
        matched.append("融资阶段在偏好阶段中出现")
    elif excluded_stages and project["financing_stage"] and project["financing_stage"] in excluded_stages:
        outside.append("融资阶段出现在排除阶段中")
    else:
        unknown.append("融资阶段匹配需要进一步确认")
    if strategy.get("requires_existing_investor") and not bundle.get("funding_analyses"):
        unknown.append("策略要求已有投资人，但当前材料未形成投资人信号")

    if outside:
        status = "outside_configured_scope"
    elif unknown:
        status = "potentially_matched_but_needs_confirmation" if matched else "unknown_due_to_missing_materials"
    else:
        status = "matched_by_current_materials"
    summary = "；".join(matched + unknown + outside) or "当前材料不足以进行策略匹配。"
    create_strategy_match(project_id, strategy_id, status, matched, unknown, outside, summary)
    return {"match_status": status, "matched_items": matched, "unknown_items": unknown, "outside_scope_items": outside, "source_summary": summary}


def generate_material_request_draft(project_id: str) -> List[Dict[str, str]]:
    bundle = get_project_bundle(project_id)
    drafts = []
    existing = {
        (item.get("material_name", "").strip(), item.get("why_needed", "").strip())
        for item in bundle.get("material_requests", [])
    }
    for task in bundle["tasks"]:
        if task["status"] != "verified" and task["suggested_materials"]:
            key = (task["suggested_materials"].strip(), task["missing_evidence"].strip())
            if key in existing:
                continue
            drafts.append(
                {
                    "material_name": task["suggested_materials"],
                    "why_needed": task["missing_evidence"],
                    "priority": task["risk_level"],
                }
            )
            create_material_request(project_id, task["suggested_materials"], task["missing_evidence"], task["risk_level"], created_by="ai")
            existing.add(key)
    return drafts


def analyze_interview_note(project_id: str, interview_note_id: str) -> Dict[str, Any]:
    bundle = get_project_bundle(project_id)
    note = next((item for item in bundle.get("interview_notes", []) if item["id"] == interview_note_id), None)
    if not note:
        raise LLMResponseError("访谈纪要不存在")
    suggestion = {
        "interview_note_id": interview_note_id,
        "summary": note.get("summary", ""),
        "possible_new_facts": [],
        "possible_gaps": ["访谈结论需要对应原始材料或第三方证据支持。"],
    }
    create_ai_suggestion(project_id, "hypothesis_status_update", "interview_note", interview_note_id, suggestion, "访谈纪要产生的事实和风险候选需要人工确认。")
    return suggestion


def explain_industry_term(project_id: str, term: str, llm: LLMClient | None = None) -> Dict[str, Any]:
    llm = llm or LLMClient()
    bundle = get_project_bundle(project_id)
    context = {
        "project": bundle["project"],
        "sector_analyses": bundle.get("sector_analyses", []),
        "industry_terms": bundle.get("industry_terms", []),
    }
    payload = llm.chat_json(
        [
            {
                "role": "system",
                "content": "你是投研行业术语解释助手。请结合项目行业上下文，用简洁中文输出 JSON。",
            },
            {
                "role": "user",
                "content": f"""
请解释行业术语，并说明它与该项目投研判断的关系。返回严格 JSON：
{{"term": "", "plain_explanation": "", "why_it_matters": "", "related_questions": ""}}

项目上下文：
{json.dumps(context, ensure_ascii=False)[:8000]}

术语：{term}
""",
            },
        ]
    )
    _assert_keys(payload, ["term", "plain_explanation", "why_it_matters", "related_questions"], "术语解释")
    return payload
