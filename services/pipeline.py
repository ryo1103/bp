from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .llm import LLMClient
from .models import LLMResponseError
from .parser import parse_document
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


def _chunks_for_prompt(chunks: List[Dict[str, Any]], limit: int = 25) -> str:
    rows = []
    for chunk in chunks[:limit]:
        file_name = chunk.get("file_name") or chunk.get("document_name") or ""
        file_prefix = f" file={file_name}" if file_name else ""
        rows.append(
            f"[chunk_id={chunk['id']}{file_prefix} page={chunk['page_number']} section={chunk['section_label']}]\n{chunk['text']}"
        )
    return "\n\n".join(rows)


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

    if not (3 <= len(payload["key_highlights"]) <= 7):
        raise LLMResponseError("最重要看点数量必须为 3-7 个")
    if len(payload["assumptions"]) < 5:
        raise LLMResponseError("关键假设至少需要 5 个")
    if len(payload["verification_tasks"]) < 5:
        raise LLMResponseError("验证任务至少需要 5 个")
    return payload


def validate_supplementary(payload: Dict[str, Any], task_ids: set[str], chunk_ids: set[str]) -> Dict[str, Any]:
    _assert_keys(payload, ["material_summary", "task_updates", "stage_recommendation", "risk_level", "updated_memo"], "补充材料验证结果")
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
  "stage_recommendation": "继续看|暂缓|不建议继续|等待补充信息",
  "risk_level": "high|medium|low",
  "initial_memo": ""
}}

要求：
- key_highlights 必须 3-7 个，且每条绑定 source_chunk_id。
- assumptions 至少 5 个。
- verification_tasks 至少 5 个。
- bp_claims 和 key_highlights 的 source_chunk_id 必须从下方 chunks 的 chunk_id 中选择。
- bp_claims 和 key_highlights 必须填写 source_page；source_page 必须等于对应 chunk 的 page。
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
) -> Dict[str, Any]:
    llm = llm or LLMClient()
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
    document = {
        "id": new_id("doc"),
        "document_type": "supplementary",
        "file_name": uploaded_name or "粘贴补充材料",
        "file_path": str(path),
        "parser": parsed.parser,
    }
    task_ids = {task["id"] for task in bundle["tasks"]}
    chunk_ids = {str(chunk["id"]) for chunk in parsed.chunks}
    history = {
        "claims": bundle["claims"],
        "assumptions": bundle["assumptions"],
        "tasks": bundle["tasks"],
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
  "stage_recommendation": "继续看|暂缓|不建议继续|等待补充信息",
  "risk_level": "high|medium|low",
  "updated_memo": ""
}}

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


def generate_memo_from_data(project_id: str) -> str:
    bundle = get_project_bundle(project_id)
    project = bundle["project"]
    lines = [
        f"# {project['company_name']} 阶段性投资分析 Memo",
        "",
        "## 项目基本信息",
        "",
        f"- 行业：{project['industry']}",
        f"- 融资阶段：{project['financing_stage']}",
        f"- 一句话介绍：{project['one_liner']}",
        f"- 当前建议：{project['current_recommendation']}",
        f"- 风险等级：{project['risk_level']}",
        "",
        "## 最重要看点",
        "",
    ]
    lines.extend(
        f"- {item['title']}：{item['why_important']}（证据充分度：{item['evidence_level']}，来源 p{item['source_page']}）"
        for item in bundle["highlights"]
    )
    lines.extend(["", "## BP 关键陈述", ""])
    lines.extend(f"- {claim['claim_text']}（状态：{claim['verification_status']}，来源 p{claim['source_page']}）" for claim in bundle["claims"])
    lines.extend(["", "## 关键假设与验证任务", ""])
    for task in bundle["tasks"]:
        lines.append(
            f"- {task['title']}｜风险：{task['risk_level']}｜状态：{task['status']}｜缺失证据：{task['missing_evidence']}"
        )
    lines.extend(["", "## 阶段性建议", "", f"{project['current_recommendation']}。该建议仅基于当前证据充分度，不构成最终投资决策。"])
    content = "\n".join(lines)
    insert_memo(project_id, content, {"type": "manual_from_structured_data"})
    return content
