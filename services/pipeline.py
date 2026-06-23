from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .llm import LLMClient
from .models import LLMResponseError
from .parser import parse_document
from .research_provider import NullResearchProvider, ResearchProvider
from .storage import (
    get_project_bundle,
    insert_memo,
    insert_supplementary_verification,
    new_id,
    replace_bp_analysis,
    save_uploaded_file,
)


VALID_STATUSES = {"unverified", "partially_verified", "verified", "unverifiable", "contradicted"}
VALID_RISKS = {"high", "medium", "low"}
VALID_RED_FLAG_STATUSES = {"open", "partially_resolved", "resolved", "contradicted"}
VALID_RED_FLAG_TYPES = {"team", "customer", "revenue", "qualification", "financing", "technology", "logic", "other"}


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
                "你是严谨的早期投资分析助手。只基于给定 BP chunks 输出 JSON。"
                "必须区分 BP 陈述和已验证事实；不得给最终投资承诺。"
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
  "stage_recommendation": "继续看|暂缓|不建议继续|等待补充信息",
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
            "content": "你是投研尽调验证助手。只基于补充材料和历史任务输出 JSON，不要自由发挥。",
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
  "stage_recommendation": "继续看|暂缓|不建议继续|等待补充信息",
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
    insert_supplementary_verification(project_id, document, parsed.chunks, payload)
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
        f"# {project['company_name']} 综合投研分析报告",
        "",
        "## 项目基本信息",
        "",
        f"- 行业：{project['industry']}",
        f"- 融资阶段：{project['financing_stage']}",
        f"- 一句话介绍：{project['one_liner']}",
        f"- 当前建议：{project['current_recommendation']}",
        f"- 风险等级：{project['risk_level']}",
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
            "## 最重要看点",
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
    lines.extend(["", "## 直接异常与红旗", ""])
    if bundle.get("red_flags"):
        lines.extend(
            f"- {flag['title']}｜严重度：{flag['severity']}｜状态：{flag['status']}｜依据：{flag['evidence']}｜影响：{flag['why_it_matters']}"
            for flag in bundle["red_flags"]
        )
    else:
        lines.append("- 未发现需要直接列出的明显逻辑或真实性异常。")
    lines.extend(["", "## 关键假设与验证任务", ""])
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
    lines.extend(["", "## 财务分析", ""])
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
    lines.extend(["", "## 阶段性建议", "", f"{project['current_recommendation']}。该建议仅基于当前证据充分度，不构成最终投资决策。"])
    return "\n".join(lines)


def generate_memo_from_data(project_id: str) -> str:
    bundle = get_project_bundle(project_id)
    content = build_report_from_bundle(bundle)
    insert_memo(project_id, content, {"type": "manual_from_structured_data"})
    return content


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
