from __future__ import annotations
import json
from typing import Dict, List, Optional

import streamlit as st

from services.llm import LLMClient
from services.models import (
    AppError,
    INDUSTRY_NODE_LABELS,
    LLMConfigError,
    LLMResponseError,
    RED_FLAG_STATUS_LABELS,
    RED_FLAG_TYPE_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
)
from services.pipeline import (
    analyze_bp_batch,
    analyze_interview_note,
    analyze_strategy_match,
    build_report_from_bundle,
    explain_industry_term,
    generate_material_request_draft,
    generate_memo_from_data,
    verify_supplementary,
)
from services.storage import (
    create_fund_strategy,
    create_material_request,
    create_manual_research_question,
    create_manual_task,
    create_project,
    delete_project,
    get_project_bundle,
    insert_interview_note,
    init_db,
    list_deal_pipeline_projects,
    list_fund_strategies,
    list_pending_ai_suggestions,
    list_projects,
    review_ai_suggestion,
    update_material_request_status,
    update_human_project_status,
    update_task,
)


st.set_page_config(page_title="AI 投研工作台", layout="wide")


AI_RESEARCH_STATE_LABELS = {
    "material_insufficient": "材料不足",
    "readable_for_initial_review": "可初读",
    "key_gaps_identified": "已识别关键缺口",
    "evidence_partially_collected": "部分证据已收集",
    "ready_for_human_review": "待人工复核",
    "memo_draft_available": "Memo 草稿可用",
}

HUMAN_PROJECT_STATUS_LABELS = {
    "inbox": "待入库",
    "initial_review": "待初读",
    "waiting_for_materials": "待补材料",
    "light_dd": "轻尽调",
    "full_dd": "完整尽调",
    "memo_drafting": "Memo 草稿",
    "ic_review": "投委会讨论",
    "invested": "已投资",
    "archived": "人工归档",
    "passed_by_human": "人工决定不继续",
    "long_term_tracking": "长期跟踪",
}

MATERIAL_STAGE_LABELS = {
    "only_bp": "仅 BP",
    "bp_plus_basic_docs": "BP + 基础材料",
    "bp_plus_financials": "BP + 财务材料",
    "bp_plus_interviews": "BP + 访谈",
    "external_sources_added": "已补外部来源",
    "multi_source_dd": "多来源尽调",
}

JUDGEMENT_READINESS_LABELS = {
    "very_limited": "非常有限",
    "limited": "有限",
    "moderate": "中等",
    "relatively_supported": "相对有支撑",
}

STRATEGY_MATCH_LABELS = {
    "unknown_due_to_missing_materials": "材料不足，暂不能判断",
    "potentially_matched_but_needs_confirmation": "可能匹配，需人工确认",
    "matched_by_current_materials": "当前材料显示匹配",
    "outside_configured_scope": "疑似不在策略范围内",
}

MATERIAL_REQUEST_STATUS_LABELS = {
    "ai_suggested": "AI 建议，待人工确认",
    "accepted_by_human": "人工已接受",
    "required": "待索取",
    "requested": "已向公司索取",
    "received": "已收到",
    "waived": "人工豁免",
}

ACTION_STATUS_LABELS = {
    "ai_suggested": "AI 建议，待人工确认",
    "open": "待执行",
    "in_progress": "进行中",
    "done": "已完成",
    "waived": "人工豁免",
}

EVIDENCE_SUFFICIENCY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "not_assessable": "暂不能判断",
    "company_claim_only": "仅材料陈述",
}

HYPOTHESIS_CATEGORY_LABELS = {
    "customer_validation": "客户验证",
    "financial_quality": "财务质量",
    "team_capability": "团队能力",
    "market_size": "市场空间",
    "business_model": "商业模式",
    "product_technology": "产品/技术",
    "funding_round_fit": "轮次与交易结构",
}

RESEARCH_ACTION_TYPE_LABELS = {
    "material_request": "索取材料",
    "financial_check": "财务核验",
    "founder_interview": "创始人访谈",
    "customer_interview": "客户访谈",
    "expert_interview": "专家访谈",
    "legal_check": "法务/合规核验",
}

RISK_ITEM_STATUS_LABELS = {
    "needs_verification": "待核验",
    "partially_resolved": "部分解释",
    "resolved": "已解释",
    "contradicted": "被反证",
    "open": "未解决",
}

MATERIAL_SOURCE_LABELS = {
    "ai": "AI 草稿",
    "human": "人工添加",
}

INTERVIEW_TYPE_LABELS = {
    "founder": "创始人",
    "customer": "客户",
    "expert": "专家",
    "internal": "内部讨论",
    "other": "其他",
}

DOCUMENT_TYPE_LABELS = {
    "bp": "BP / 商业计划书",
    "supplementary": "补充材料",
}

DOCUMENT_STATUS_LABELS = {
    "completed": "已解析",
    "pending": "待解析",
    "failed": "解析失败",
}

EVIDENCE_JUDGMENT_LABELS = {
    "supports": "支持",
    "partially_supports": "部分支持",
    "contradicts": "反证",
    "unclear": "不明确",
}

RESOLUTION_STATUS_LABELS = {
    "resolved": "已解决",
    "partially_resolved": "部分解决",
    "contradicted": "被反证",
    "new_information": "新增信息",
    "irrelevant": "未解决原问题",
}

LOW_AUTHORITY_NOTICE = "本平台不替代研究员做投资决策。以下内容仅基于当前上传材料生成，用于帮助整理事实、假设、证据、风险和下一步验证动作。"


def style() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stMetricValue"] { font-size: 1.45rem; }
        div[data-testid="stTabs"] button { font-size: 0.95rem; }
        .small-muted { color: #667064; font-size: 0.86rem; }
        .status-pill {
          display:inline-block; padding:2px 8px; border-radius:999px;
          border:1px solid #d8ded5; font-size:12px; margin-right:4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def pill(text: str) -> str:
    return f'<span class="status-pill">{text}</span>'


def field_card(label: str, value: object) -> None:
    st.caption(label)
    display_value = "待确认" if value is None or value == "" else value
    st.markdown(f"**{display_value}**")


def json_list(value: object) -> List[object]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def top_unverified_assumptions(bundle: Dict[str, object], limit: int = 3) -> List[Dict[str, object]]:
    return [item for item in bundle.get("assumptions", []) if item.get("current_status") != "verified"][:limit]


def top_open_risks(bundle: Dict[str, object], limit: int = 3) -> List[Dict[str, object]]:
    return build_red_flag_rows(bundle)[:limit]


def top_open_tasks(bundle: Dict[str, object], limit: int = 3) -> List[Dict[str, object]]:
    return [item for item in bundle.get("tasks", []) if item.get("status") != "verified"][:limit]


def task_ids_for_assumption(bundle: Dict[str, object], assumption_id: str) -> List[str]:
    return [
        str(task.get("id"))
        for task in bundle.get("tasks", [])
        if task.get("linked_assumption_id") == assumption_id
    ]


def evidence_for_task_ids(bundle: Dict[str, object], task_ids: List[str]) -> List[Dict[str, object]]:
    task_id_set = set(task_ids)
    return [item for item in bundle.get("evidence", []) if item.get("task_id") in task_id_set]


def status_timestamp(items: List[Dict[str, object]]) -> str:
    timestamps = [str(item.get("updated_at") or item.get("created_at") or "") for item in items if item.get("updated_at") or item.get("created_at")]
    return max(timestamps) if timestamps else ""


def related_object_for_red_flag(flag: Dict[str, object], bundle: Dict[str, object]) -> str:
    source_page = flag.get("source_page")
    for claim in bundle.get("claims", []):
        if claim.get("source_page") == source_page:
            return f"材料陈述：{str(claim.get('claim_text', ''))[:40]}"
    flag_text = " ".join(
        [
            str(flag.get("title", "")),
            str(flag.get("evidence", "")),
            str(flag.get("why_it_matters", "")),
        ]
    )
    for assumption in bundle.get("assumptions", []):
        words = [word for word in str(assumption.get("assumption_text", "")).replace("，", " ").replace("。", " ").split() if len(word) >= 2]
        if any(word in flag_text for word in words[:4]):
            return f"待验证主线：{str(assumption.get('assumption_text', ''))[:40]}"
    return "材料陈述：来源页待核对"


def build_red_flag_rows(bundle: Dict[str, object]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for flag in bundle.get("red_flags", []):
        if flag.get("status") != "resolved":
            rows.append(
                {
                    "title": flag.get("title", ""),
                    "category": RED_FLAG_TYPE_LABELS.get(flag.get("flag_type"), flag.get("flag_type", "")),
                    "status": RED_FLAG_STATUS_LABELS.get(flag.get("status"), flag.get("status", "")),
                    "severity": RISK_LABELS.get(flag.get("severity"), flag.get("severity", "")),
                    "description": flag.get("why_it_matters") or flag.get("evidence", ""),
                    "evidence": flag.get("evidence", ""),
                    "source_page": flag.get("source_page"),
                    "related_object": related_object_for_red_flag(flag, bundle),
                    "suggested_verification": flag.get("suggested_verification", ""),
                    "updated_at": flag.get("updated_at", ""),
                }
            )
    return rows


def build_evidence_rows(bundle: Dict[str, object]) -> List[Dict[str, object]]:
    task_by_id = {item.get("id"): item for item in bundle.get("tasks", [])}
    return [
        {
            "事实/证据": item.get("evidence_text", ""),
            "判断": EVIDENCE_JUDGMENT_LABELS.get(item.get("judgment"), item.get("judgment", "")),
            "置信度": item.get("confidence", ""),
            "关联核验计划": task_by_id.get(item.get("task_id"), {}).get("title", item.get("task_id", "")),
            "来源材料": item.get("document_id", ""),
            "时间": item.get("created_at", ""),
        }
        for item in bundle.get("evidence", [])
    ]


def build_assumption_backbone_rows(bundle: Dict[str, object]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    risks = build_red_flag_rows(bundle)
    for assumption in bundle.get("assumptions", []):
        assumption_id = str(assumption.get("id", ""))
        linked_tasks = [task for task in bundle.get("tasks", []) if task.get("linked_assumption_id") == assumption_id]
        linked_task_ids = [str(task.get("id")) for task in linked_tasks]
        linked_evidence = evidence_for_task_ids(bundle, linked_task_ids)
        risk_hits = [
            risk for risk in risks
            if str(assumption.get("assumption_text", ""))[:12] and str(assumption.get("assumption_text", ""))[:12] in str(risk.get("related_object", ""))
        ]
        current_basis = "；".join([str(task.get("existing_evidence", "")) for task in linked_tasks if task.get("existing_evidence")]) or "BP 材料陈述，待补充外部证据"
        rows.append(
            {
                "维度": RISK_LABELS.get(assumption.get("risk_level"), assumption.get("risk_level", "")),
                "待验证主线": assumption.get("assumption_text", ""),
                "为什么重要": assumption.get("why_it_matters") or assumption.get("importance", ""),
                "当前依据": current_basis,
                "证据数": len(linked_evidence),
                "待核验风险数": len(risk_hits),
                "未完成待办数": len([task for task in linked_tasks if task.get("status") != "verified"]),
                "当前状态": STATUS_LABELS.get(assumption.get("current_status"), assumption.get("current_status", "")),
                "下一步": "去问题核验查看当前材料回答；去尽调执行处理任务",
                "_updated_at": status_timestamp([assumption] + linked_tasks + linked_evidence),
            }
        )
    return rows


def build_verification_summary_rows(bundle: Dict[str, object]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    risk_rows = build_red_flag_rows(bundle)
    for assumption in bundle.get("assumptions", []):
        assumption_id = str(assumption.get("id", ""))
        linked_tasks = [task for task in bundle.get("tasks", []) if task.get("linked_assumption_id") == assumption_id]
        linked_evidence = evidence_for_task_ids(bundle, [str(task.get("id")) for task in linked_tasks])
        support_count = len([item for item in linked_evidence if item.get("judgment") in {"supports", "partially_supports"}])
        unclear_count = len([item for item in linked_evidence if item.get("judgment") in {"contradicts", "unclear"}])
        risk_count = len(
            [
                risk for risk in risk_rows
                if str(assumption.get("assumption_text", ""))[:12] and str(assumption.get("assumption_text", ""))[:12] in str(risk.get("related_object", ""))
            ]
        )
        rows.append(
            {
                "待验证主线": assumption.get("assumption_text", ""),
                "当前状态": STATUS_LABELS.get(assumption.get("current_status"), assumption.get("current_status", "")),
                "支持证据数": support_count,
                "反证/不明确证据数": unclear_count,
                "待核验风险数": risk_count,
                "最近更新": status_timestamp([assumption] + linked_tasks + linked_evidence),
            }
        )
    return rows


def evidence_answer_state(evidence_items: List[Dict[str, object]]) -> Dict[str, object]:
    judgments = [str(item.get("judgment", "")) for item in evidence_items]
    if "contradicts" in judgments:
        return {"answer": "出现反证或冲突", "level": "反证/冲突", "rank": 4}
    if "partially_supports" in judgments:
        return {"answer": "已有材料部分支持", "level": "部分支持", "rank": 3}
    if "supports" in judgments:
        return {"answer": "已有材料支持", "level": "支持", "rank": 2}
    if "unclear" in judgments:
        return {"answer": "材料不明确，仍需补充", "level": "不明确", "rank": 1}
    return {"answer": "仅 BP 提出，暂无补充材料证据", "level": "无补充证据", "rank": 0}


def build_question_threads(bundle: Dict[str, object]) -> List[Dict[str, object]]:
    """把 assumption / task / evidence / red_flag / material_request 组装成以研究问题为中心的线程。"""
    threads: List[Dict[str, object]] = []
    tasks = bundle.get("tasks", [])
    evidence = bundle.get("evidence", [])
    for assumption in bundle.get("assumptions", []):
        assumption_id = str(assumption.get("id", ""))
        linked_tasks = [task for task in tasks if task.get("linked_assumption_id") == assumption_id]
        linked_task_ids = [str(task.get("id")) for task in linked_tasks]
        linked_evidence = evidence_for_task_ids(bundle, linked_task_ids)
        answer_state = evidence_answer_state(linked_evidence)
        missing_items = [str(task.get("missing_evidence", "")) for task in linked_tasks if task.get("status") != "verified" and task.get("missing_evidence")]
        threads.append(
            {
                "assumption": assumption,
                "tasks": linked_tasks,
                "evidence": linked_evidence,
                "answer_state": answer_state,
                "risk_count": len([flag for flag in bundle.get("red_flags", []) if flag.get("status") != "resolved"]),
                "open_task_count": len([task for task in linked_tasks if task.get("status") != "verified"]),
                "missing": "；".join(missing_items[:2]) or "暂无明确缺口，需研究员判断是否继续补证。",
                "latest_update": status_timestamp([assumption] + linked_tasks + linked_evidence),
            }
        )
    return threads


def question_thread_summary_rows(threads: List[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for thread in threads:
        assumption = thread["assumption"]
        evidence_items = thread["evidence"]
        answer_state = thread["answer_state"]
        rows.append(
            {
                "研究问题": assumption.get("assumption_text", ""),
                "来源": "人工添加" if str(assumption.get("id", "")).startswith("manual_assumption_") else "BP 初读",
                "当前材料回答": answer_state["answer"],
                "证据状态": f"{len(evidence_items)} 条；最高判断：{answer_state['level']}",
                "待核验风险": thread["risk_count"],
                "未完成尽调动作": thread["open_task_count"],
                "仍缺什么": thread["missing"],
            }
        )
    return rows


def render_manual_research_question_form(project_id: str) -> None:
    with st.expander("＋ 添加研究问题", expanded=False):
        with st.form(f"manual_research_question_{project_id}"):
            assumption_text = st.text_area("研究问题", placeholder="例如：客户是否愿意持续为该系统付费？")
            dimension = st.selectbox("维度", ["市场", "客户", "产品技术", "商业模式", "财务质量", "团队", "轮次交易", "其他"])
            why_it_matters = st.text_area("为什么重要")
            failure_impact = st.text_area("如果无法验证会影响什么")
            source_note = st.text_area("当前材料线索")
            verification_method = st.text_area("建议核验方式")
            human_note = st.text_input("人工备注")
            if st.form_submit_button("保存研究问题", type="primary"):
                if not assumption_text.strip() or not why_it_matters.strip() or not verification_method.strip():
                    st.warning("请至少填写研究问题、为什么重要和建议核验方式。")
                else:
                    create_manual_research_question(
                        project_id,
                        assumption_text,
                        dimension,
                        "medium",
                        why_it_matters,
                        failure_impact,
                        verification_method,
                        source_note=source_note,
                        human_note=human_note,
                        created_by=st.session_state.get("display_name", "本地研究员"),
                    )
                    st.success("已添加研究问题。")
                    st.rerun()


def render_claim_subset_section(title: str, bundle: Dict[str, object], keywords: List[str]) -> None:
    claims = [
        claim for claim in bundle.get("claims", [])
        if any(keyword in str(claim.get("topic", "")) or keyword in str(claim.get("claim_text", "")) for keyword in keywords)
    ]
    st.markdown(f"#### {title}")
    if not claims:
        st.info("当前材料中暂无该维度的明确陈述。")
        return
    st.dataframe(
        [
            {
                "陈述内容": item["claim_text"],
                "主题": item["topic"],
                "核验状态": STATUS_LABELS.get(item["verification_status"], item["verification_status"]),
                "来源页": item["source_page"],
                "原文摘录": item["source_quote"],
            }
            for item in claims
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_global_term_assistant(project_id: str) -> None:
    state_key = f"global_term_result_{project_id}"
    form_key = f"global_term_assistant_float_{project_id}"
    st.markdown(
        """
        <style>
        div[data-testid="stPopover"] {
          position: fixed;
          right: 18px;
          bottom: 18px;
          z-index: 9999;
        }
        div[data-testid="stPopover"] > button {
          min-width: 48px;
          width: 48px;
          min-height: 48px;
          height: 48px;
          border-radius: 999px;
          padding: 0 !important;
          font-size: 24px;
          font-weight: 700;
          line-height: 1;
          box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
          border: 1px solid #cbd5e1;
          background: #ffffff;
        }
        div[data-testid="stPopover"] > button:hover {
          border-color: #64748b;
          box-shadow: 0 10px 28px rgba(15, 23, 42, 0.22);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.popover("💬", help="随手问行业/术语"):
        st.markdown("#### 随手问")
        st.caption("临时查询行业名词、材料概念或投研口径；回答结合当前项目上下文，不改变项目状态。")
        with st.form(form_key):
            query = st.text_input("问题或术语", placeholder="例如：客户集中度、DRG、回款周期、垂直 SaaS")
            submitted = st.form_submit_button("提问")
            if submitted:
                if not query.strip():
                    st.warning("请输入要查询的问题或术语。")
                else:
                    try:
                        with st.spinner("正在结合当前项目上下文回答..."):
                            result = explain_industry_term(project_id, query.strip(), LLMClient())
                        st.session_state[state_key] = result
                    except (LLMConfigError, LLMResponseError, AppError, Exception) as exc:
                        st.error(str(exc))
        result = st.session_state.get(state_key)
        if result:
            st.markdown(f"**{result.get('term', '查询结果')}**")
            st.write(result.get("plain_explanation", ""))
            if result.get("why_it_matters"):
                st.caption(f"为什么重要：{result['why_it_matters']}")
            if result.get("related_questions"):
                st.caption(f"可以继续问：{result['related_questions']}")


def current_project_id(projects: List[Dict[str, object]]) -> str | None:
    if "project_id" not in st.session_state and projects:
        st.session_state.project_id = projects[0]["id"]
    if not projects:
        return None
    ids = {project["id"] for project in projects}
    if st.session_state.get("project_id") not in ids:
        st.session_state.project_id = projects[0]["id"]
    return st.session_state.get("project_id")


def sidebar(projects: List[Dict[str, object]]) -> str | None:
    st.sidebar.title("投研验证工作台")
    st.sidebar.caption("BP 分析 · 假设验证 · Memo")

    with st.sidebar.expander("创建项目", expanded=not projects):
        with st.form("create_project"):
            company_name = st.text_input("公司名称", placeholder="例如：启明智能")
            st.caption("行业、融资阶段和一句话介绍会在上传 BP 后自动识别。")
            if st.form_submit_button("创建项目", use_container_width=True):
                if not company_name.strip():
                    st.warning("请填写公司名称")
                else:
                    st.session_state.project_id = create_project(company_name)
                    st.rerun()

    project_id = current_project_id(projects)
    if projects:
        labels = {
            f"{project['company_name']}｜{project['industry']}｜待核验高强度事项 {project['unverified_high_risk_count']}": project["id"]
            for project in projects
        }
        current_label = next((label for label, pid in labels.items() if pid == project_id), list(labels)[0])
        selected = st.sidebar.radio("项目列表", list(labels), index=list(labels).index(current_label))
        project_id = labels[selected]
        st.session_state.project_id = project_id
        if st.sidebar.button("删除当前项目", use_container_width=True, type="secondary"):
            delete_project(project_id)
            st.session_state.pop("project_id", None)
            st.rerun()
    else:
        st.sidebar.info("暂无项目，先创建一个项目。")
    return project_id


def uploaded_bytes(uploaded_file) -> bytes:
    if not uploaded_file:
        return b""
    return uploaded_file.getvalue()


def show_project_header(bundle: Dict[str, object]) -> None:
    project = bundle["project"]
    left, right = st.columns([2, 1])
    with left:
        st.title(project["company_name"])
        st.caption(project["one_liner"])
        st.markdown(
            " ".join(
                [
                    pill(project["industry"]),
                    pill(project["financing_stage"]),
                    pill(f"待核验风险强度：{RISK_LABELS.get(project['risk_level'], project['risk_level'])}"),
                    pill(project["current_recommendation"]),
                ]
            ),
            unsafe_allow_html=True,
        )
    with right:
        st.metric("高强度待核验事项", project["unverified_high_risk_count"])
        st.metric("已完成人工核验动作", project["verified_count"])


def render_project_header(project_id: str) -> None:
    bundle = get_project_bundle(project_id)
    project = bundle["project"]
    st.info(LOW_AUTHORITY_NOTICE)
    st.title(project["company_name"])
    st.caption(project["one_liner"])
    cols = st.columns(5)
    with cols[0]:
        field_card("材料阶段", MATERIAL_STAGE_LABELS.get(project.get("material_stage"), project.get("material_stage")))
    with cols[1]:
        field_card("材料成熟度", JUDGEMENT_READINESS_LABELS.get(project.get("judgement_readiness"), project.get("judgement_readiness")))
    with cols[2]:
        field_card("材料分析进度", AI_RESEARCH_STATE_LABELS.get(project.get("ai_research_state"), project.get("ai_research_state")))
    with cols[3]:
        field_card("项目阶段", HUMAN_PROJECT_STATUS_LABELS.get(project.get("human_project_status"), project.get("human_project_status")))
    with cols[4]:
        field_card("待确认变更", project.get("pending_ai_suggestion_count", project.get("pending_ai_updates_count", 0)))

    metric_cols = st.columns(5)
    with metric_cols[0]:
        evidence_status = project.get("evidence_sufficiency", "low")
        st.metric("证据支撑", EVIDENCE_SUFFICIENCY_LABELS.get(evidence_status, evidence_status))
    with metric_cols[1]:
        st.metric("研究问题", len([item for item in bundle["assumptions"] if item["current_status"] != "verified"]))
    with metric_cols[2]:
        st.metric("待核验风险", bundle["project"].get("pending_risk_count", len([flag for flag in bundle.get("red_flags", []) if flag["status"] != "resolved"])))
    with metric_cols[3]:
        st.metric("核验计划", len([task for task in bundle["tasks"] if task["status"] != "verified"]))
    with metric_cols[4]:
        strategy_status = project.get("strategy_match_status", "unknown_due_to_missing_materials")
        st.metric("策略匹配", STRATEGY_MATCH_LABELS.get(strategy_status, strategy_status))


def render_deal_pipeline() -> None:
    st.title("项目池")
    st.info(LOW_AUTHORITY_NOTICE)
    last_update = st.session_state.pop("last_human_status_update", None)
    if last_update:
        status_label = HUMAN_PROJECT_STATUS_LABELS.get(last_update["new_status"], last_update["new_status"])
        st.success(f"{last_update['company_name']} 的项目阶段已更新为：{status_label}")
    projects = list_deal_pipeline_projects()
    if not projects:
        st.info("暂无项目。请先在左侧创建项目，上传 BP 后开始初筛。")
        return

    grouped = {status: [] for status in HUMAN_PROJECT_STATUS_LABELS}
    for project in projects:
        grouped.setdefault(project.get("human_project_status") or "inbox", []).append(project)

    for status, label in HUMAN_PROJECT_STATUS_LABELS.items():
        items = grouped.get(status, [])
        if not items:
            continue
        st.markdown(f"### {label} · {len(items)}")
        for project in items:
            with st.container(border=True):
                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.markdown(f"**{project['company_name']}**")
                    st.caption(project["one_liner"])
                    st.caption(f"赛道候选：{project['industry']}｜融资轮次陈述：{project['financing_stage']}")
                with cols[1]:
                    st.write(f"材料阶段：{MATERIAL_STAGE_LABELS.get(project.get('material_stage'), project.get('material_stage'))}")
                    st.write(f"材料成熟度：{JUDGEMENT_READINESS_LABELS.get(project.get('judgement_readiness'), project.get('judgement_readiness'))}")
                    st.caption(f"材料分析进度：{AI_RESEARCH_STATE_LABELS.get(project.get('ai_research_state'), project.get('ai_research_state'))}")
                with cols[2]:
                    evidence_status = project.get("evidence_sufficiency", "low")
                    strategy_status = project.get("strategy_match_status", "unknown_due_to_missing_materials")
                    st.write(f"证据支撑：{EVIDENCE_SUFFICIENCY_LABELS.get(evidence_status, evidence_status)}")
                    st.write(f"研究问题：{project.get('task_count', 0) - project.get('verified_count', 0)}")
                    st.write(f"待核验风险：{project.get('pending_risk_count', 0)}")
                    st.caption(f"策略匹配：{STRATEGY_MATCH_LABELS.get(strategy_status, strategy_status)}")
                with cols[3]:
                    if st.button("打开项目", key=f"open_{project['id']}"):
                        st.session_state.project_id = project["id"]
                        st.session_state.page = "项目详情"
                        st.rerun()


def render_fund_strategy_settings() -> None:
    st.title("投资策略")
    st.info(
        "这里用于沉淀基金的投资偏好和硬性红线，例如关注赛道、排除赛道、偏好轮次、单笔金额、目标持股、收入/毛利要求和产业协同偏好。"
        "系统会把项目材料与已配置策略进行对照，生成“策略匹配”过程信号，帮助研究员判断项目是否值得继续看、还缺哪些材料。"
        "该信号不会自动给出投资建议，也不会自动改变项目阶段。"
    )
    with st.form("fund_strategy"):
        strategy_name = st.text_input("策略名称", value="默认策略")
        focus_sectors = st.text_area("关注赛道", placeholder="例如：企业服务、AI 应用、半导体")
        excluded_sectors = st.text_area("排除赛道")
        preferred_stages = st.text_input("偏好轮次", placeholder="例如：天使轮、Pre-A、A 轮")
        excluded_stages = st.text_input("排除轮次")
        cols = st.columns(2)
        with cols[0]:
            ticket_size_min = st.number_input("单笔金额下限", min_value=0.0, value=0.0)
            target_ownership_min = st.number_input("目标持股下限 %", min_value=0.0, value=0.0)
        with cols[1]:
            ticket_size_max = st.number_input("单笔金额上限", min_value=0.0, value=0.0)
            target_ownership_max = st.number_input("目标持股上限 %", min_value=0.0, value=0.0)
        geography_preference = st.text_input("地域偏好")
        revenue_requirement = st.text_input("收入要求")
        gross_margin_requirement = st.text_input("毛利率要求")
        customer_type_preference = st.text_input("客户类型偏好")
        long_rd_cycle_allowed = st.checkbox("允许长研发周期", value=True)
        industrial_synergy_preferred = st.checkbox("偏好产业协同", value=False)
        requires_existing_investor = st.checkbox("要求已有投资人", value=False)
        hard_redlines = st.text_area("硬性红线")
        soft_preferences = st.text_area("软性偏好")
        if st.form_submit_button("保存策略", type="primary"):
            create_fund_strategy(
                {
                    "strategy_name": strategy_name,
                    "focus_sectors": focus_sectors,
                    "excluded_sectors": excluded_sectors,
                    "preferred_stages": preferred_stages,
                    "excluded_stages": excluded_stages,
                    "ticket_size_min": ticket_size_min or None,
                    "ticket_size_max": ticket_size_max or None,
                    "target_ownership_min": target_ownership_min or None,
                    "target_ownership_max": target_ownership_max or None,
                    "geography_preference": geography_preference,
                    "revenue_requirement": revenue_requirement,
                    "gross_margin_requirement": gross_margin_requirement,
                    "customer_type_preference": customer_type_preference,
                    "long_rd_cycle_allowed": long_rd_cycle_allowed,
                    "industrial_synergy_preferred": industrial_synergy_preferred,
                    "requires_existing_investor": requires_existing_investor,
                    "hard_redlines": hard_redlines,
                    "soft_preferences": soft_preferences,
                    "created_by": st.session_state.get("display_name", "本地研究员"),
                }
            )
            st.success("策略已保存")
            st.rerun()

    st.markdown("#### 已配置策略")
    strategies = list_fund_strategies()
    if strategies:
        st.dataframe(
            [
                {
                    "策略": item["strategy_name"],
                    "关注赛道": item["focus_sectors"],
                    "偏好轮次": item["preferred_stages"],
                    "硬性红线": item["hard_redlines"],
                    "更新": item["updated_at"],
                }
                for item in strategies
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无基金策略。")


def memo_from_bundle(bundle: Dict[str, object]) -> str:
    return build_report_from_bundle(bundle)


def render_suggestion_payload(suggestion: Dict[str, object]) -> None:
    payload = json.loads(str(suggestion["suggested_change_json"] or "{}"))
    target_type = suggestion.get("target_object_type")
    if target_type == "verification_task":
        st.write(f"建议状态：{STATUS_LABELS.get(payload.get('new_status'), payload.get('new_status', '待确认'))}")
        if payload.get("evidence_text"):
            st.write(f"证据：{payload['evidence_text']}")
        if payload.get("still_missing"):
            st.caption(f"仍缺：{payload['still_missing']}")
        if payload.get("new_questions"):
            st.caption(f"新问题：{payload['new_questions']}")
    elif target_type == "red_flag":
        st.write(f"建议状态：{RED_FLAG_STATUS_LABELS.get(payload.get('new_status'), payload.get('new_status', '待确认'))}")
        if payload.get("impact_summary"):
            st.write(f"影响：{payload['impact_summary']}")
        if payload.get("remaining_gap"):
            st.caption(f"仍缺：{payload['remaining_gap']}")
    else:
        st.json(payload)


def render_pending_ai_suggestions(project_id: str) -> None:
    suggestions = list_pending_ai_suggestions(project_id)
    if not suggestions:
        st.info("暂无待确认变更。")
        return
    st.warning(f"有 {len(suggestions)} 条材料带来的状态变更建议，待人工确认。系统不会自动改变项目阶段、确认风险或关闭待办。")
    for suggestion in suggestions:
        with st.container(border=True):
            st.markdown(f"**{suggestion['suggestion_type']}**")
            st.caption(f"对象：{suggestion['target_object_type']}｜原因：{suggestion['ai_reason']}")
            render_suggestion_payload(suggestion)
            cols = st.columns(3)
            with cols[0]:
                if st.button("接受并应用", key=f"accept_{suggestion['id']}"):
                    review_ai_suggestion(suggestion["id"], "accept", reviewed_by=st.session_state.get("display_name", "本地研究员"))
                    st.rerun()
            with cols[1]:
                if st.button("忽略", key=f"ignore_{suggestion['id']}"):
                    review_ai_suggestion(suggestion["id"], "ignore", reviewed_by=st.session_state.get("display_name", "本地研究员"))
                    st.rerun()
            with cols[2]:
                if st.button("标记为需要复核", key=f"review_{suggestion['id']}"):
                    review_ai_suggestion(suggestion["id"], "needs_review", reviewed_by=st.session_state.get("display_name", "本地研究员"))
                    st.rerun()


def upload_bp_tab(project_id: str, bundle: Dict[str, object]) -> None:
    has_bp_analysis = bool(bundle["claims"] or bundle["highlights"] or bundle["assumptions"])
    st.subheader("项目速览")
    project = bundle["project"]
    info_cols = st.columns(4)
    with info_cols[0]:
        field_card("公司", project["company_name"])
    with info_cols[1]:
        field_card("行业", project["industry"])
    with info_cols[2]:
        field_card("融资阶段", project["financing_stage"])
    with info_cols[3]:
        field_card("当前提示", project["current_recommendation"])

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("材料陈述", len(bundle["claims"]))
    with metric_cols[1]:
        st.metric("初步亮点", len(bundle["highlights"]))
    with metric_cols[2]:
        st.metric("待验证判断", len(bundle["assumptions"]))
    with metric_cols[3]:
        st.metric("尽调动作", len(bundle["tasks"]))

    open_flags = [flag for flag in bundle.get("red_flags", []) if flag["status"] != "resolved"]
    if open_flags:
        st.markdown("#### 疑似异常 / 待核验风险")
        for flag in open_flags[:3]:
            with st.container(border=True):
                st.markdown(f"**{flag['title']}**")
                st.caption(
                    f"类型：{RED_FLAG_TYPE_LABELS.get(flag['flag_type'], flag['flag_type'])}｜严重度：{RISK_LABELS.get(flag['severity'], flag['severity'])}｜状态：{RED_FLAG_STATUS_LABELS.get(flag['status'], flag['status'])}"
                )
                st.write(flag["why_it_matters"])

    funding_items = bundle.get("funding_analyses", [])
    if funding_items:
        funding = funding_items[-1]
        st.markdown("#### 融资轮次判断")
        with st.container(border=True):
            cols = st.columns(4)
            with cols[0]:
                field_card("BP 声称轮次", funding["stated_round"] or project["financing_stage"])
            with cols[1]:
                field_card("反推轮次", funding["inferred_round"])
            with cols[2]:
                field_card("资料充分度", funding["material_sufficiency"])
            with cols[3]:
                field_card("投资人信号", funding["investor_signal"])

    high_risk_tasks = [
        task for task in bundle["tasks"] if task["risk_level"] == "high" and task["status"] != "verified"
    ]
    st.markdown("#### 高强度待核验事项")
    if high_risk_tasks:
        for task in high_risk_tasks[:5]:
            with st.container(border=True):
                st.markdown(f"**{task['title']}**")
                st.caption(
                    f"状态：{STATUS_LABELS.get(task['status'], task['status'])}｜缺失证据：{task['missing_evidence']}"
                )
    else:
        st.info("暂无高强度待核验事项。")

    st.divider()
    st.markdown("#### 已上传材料")
    if bundle["documents"]:
        for document in bundle["documents"]:
            with st.container(border=True):
                cols = st.columns([2, 1, 1])
                with cols[0]:
                    st.markdown(f"**{document['file_name']}**")
                with cols[1]:
                    st.caption(f"类型：{DOCUMENT_TYPE_LABELS.get(document['document_type'], document['document_type'])}")
                with cols[2]:
                    st.caption(f"状态：{DOCUMENT_STATUS_LABELS.get(document['parse_status'], document['parse_status'])}")
                st.write(document["summary"] or "暂无摘要")
    else:
        st.info("暂无已上传材料。")

    st.divider()
    st.subheader("BP 上传与 AI 综合分析" if not has_bp_analysis else "BP / 项目基础材料重新分析")
    if has_bp_analysis:
        st.caption("新版 BP、业务补充说明、会影响项目基本判断的材料放这里；合同、访谈纪要、财务明细等尽调证据放到“补充材料”。")
    else:
        st.caption("可一次上传多个 BP 文件，也可以直接粘贴正文。")
    with st.form(f"upload_bp_{project_id}"):
        uploaded_files = st.file_uploader(
            "BP 文件",
            type=["txt", "md", "csv", "xlsx", "pdf", "docx", "pptx"],
            accept_multiple_files=True,
        )
        pasted = st.text_area("或粘贴 BP 正文 / 追加说明", height=180)
        submitted = st.form_submit_button("上传并调用 AI 分析" if not has_bp_analysis else "用现有和新增基础材料重新分析", type="primary")
        if submitted:
            uploads = [{"name": file.name, "content": uploaded_bytes(file)} for file in (uploaded_files or [])]
            if not uploads and not pasted.strip() and not has_bp_analysis:
                st.warning("请至少上传一个 BP 文件或粘贴 BP 正文。")
                return
            if not uploads and not pasted.strip() and has_bp_analysis:
                st.info("未添加新材料，将基于现有 BP / 基础材料重新分析。")
            try:
                with st.spinner("正在解析材料并调用 AI 综合分析..."):
                    analyze_bp_batch(
                        project_id,
                        uploads,
                        pasted,
                        include_existing=has_bp_analysis,
                        llm=LLMClient(),
                    )
                st.success("BP 综合分析完成")
                st.rerun()
            except (LLMConfigError, LLMResponseError, AppError, Exception) as exc:
                st.error(str(exc))


def bp_analysis_tab(bundle: Dict[str, object]) -> None:
    st.subheader("公司与业务")
    project = bundle["project"]
    info_cols = st.columns(4)
    with info_cols[0]:
        field_card("公司", project["company_name"])
    with info_cols[1]:
        field_card("行业", project["industry"])
    with info_cols[2]:
        field_card("融资阶段", project["financing_stage"])
    with info_cols[3]:
        field_card("待核验风险强度", RISK_LABELS.get(project["risk_level"], project["risk_level"]))
    st.caption("一句话介绍")
    st.markdown(f"**{project['one_liner'] or '待确认'}**")

    st.subheader("初步亮点")
    if bundle["highlights"]:
        for item in bundle["highlights"]:
            with st.container(border=True):
                st.markdown(f"**{item['title']}**")
                st.write(item["why_important"])
                st.caption(
                    f"对应说法：{item['linked_claim_text']}｜来源 p{item['source_page']}｜证据支撑：{item['evidence_level']}｜验证方向：{item['verification_direction']}"
                )
    else:
        st.info("上传 BP 并完成分析后显示初步亮点。")

    st.subheader("材料陈述")
    st.caption("从 BP / 项目材料中抽取的可追溯陈述，尚不代表已验证事实。")
    st.dataframe(
        [
            {
                "陈述内容": item["claim_text"],
                "陈述类型": item["claim_type"],
                "主题": item["topic"],
                "核验状态": STATUS_LABELS.get(item["verification_status"], item["verification_status"]),
                "来源页": item["source_page"],
                "原文摘录": item["source_quote"],
            }
            for item in bundle["claims"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("待验证判断")
    st.dataframe(
        [
            {
                "假设": item["assumption_text"],
                "重要性": item["importance"],
                "风险": RISK_LABELS.get(item["risk_level"], item["risk_level"]),
                "状态": STATUS_LABELS.get(item["current_status"], item["current_status"]),
                "验证方法": item["verification_method"],
                "不成立影响": item["failure_impact"],
            }
            for item in bundle["assumptions"]
        ],
        use_container_width=True,
        hide_index=True,
    )


def sector_tab(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("行业与产业图")
    sector = bundle.get("sector_analyses", [])
    if sector:
        item = sector[-1]
        cols = st.columns(3)
        with cols[0]:
            field_card("一级行业", item["primary_industry"])
        with cols[1]:
            field_card("细分赛道", item["sub_sector"])
        with cols[2]:
            field_card("价值链位置", item["value_chain_position"])
        st.write(item["summary"])
        detail_cols = st.columns(3)
        with detail_cols[0]:
            field_card("目标客户", item["target_customer"])
        with detail_cols[1]:
            field_card("替代对象", item["replacement_target"])
        with detail_cols[2]:
            field_card("利润池判断", item["profit_pool_logic"])
    else:
        st.info("完成 BP 分析后显示赛道归类和产业链位置。")

    st.markdown("#### 产业图")
    if bundle.get("industry_map_nodes"):
        st.dataframe(
            [
                {
                    "环节": INDUSTRY_NODE_LABELS.get(node["node_type"], node["node_type"]),
                    "节点": node["label"],
                    "说明": node["description"],
                    "公司位置": "是" if node["is_company_position"] else "",
                }
                for node in bundle["industry_map_nodes"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无产业图节点。")

    st.markdown("#### 行业关键词")
    if bundle.get("industry_terms"):
        for term in bundle["industry_terms"]:
            with st.container(border=True):
                st.markdown(f"**{term['term']}**")
                st.write(term["explanation"])
                st.caption(f"与本项目关系：{term['relevance']}")
    else:
        st.info("暂无关键词解释。")


def red_flags_tab(bundle: Dict[str, object]) -> None:
    st.subheader("风险与异常")
    st.caption("这里展示疑似异常和待核验风险；AI 不会把这些问题标记为确认风险。")
    if bundle.get("red_flags"):
        for flag in bundle["red_flags"]:
            with st.container(border=True):
                cols = st.columns([3, 1, 1])
                with cols[0]:
                    st.markdown(f"**{flag['title']}**")
                    st.caption(f"类型：{RED_FLAG_TYPE_LABELS.get(flag['flag_type'], flag['flag_type'])}｜来源 p{flag['source_page']}")
                with cols[1]:
                    st.write(f"严重度：{RISK_LABELS.get(flag['severity'], flag['severity'])}")
                with cols[2]:
                    st.write(f"状态：{RED_FLAG_STATUS_LABELS.get(flag['status'], flag['status'])}")
                st.write(f"依据：{flag['evidence']}")
                st.write(f"为什么重要：{flag['why_it_matters']}")
                st.caption(f"可选核验方式：{flag['suggested_verification']}")
                if flag["resolution_note"]:
                    st.info(f"解决说明：{flag['resolution_note']}")
    else:
        st.info("未发现需要直接列出的明显逻辑或真实性异常。")


def funding_tab(bundle: Dict[str, object]) -> None:
    st.subheader("轮次与投资人")
    funding_items = bundle.get("funding_analyses", [])
    if not funding_items:
        st.info("完成 BP 分析后显示融资轮次、资料充分度、风险收益和投资人信号。")
        return

    funding = funding_items[-1]
    top = st.columns(3)
    with top[0]:
        field_card("BP 声称轮次", funding["stated_round"])
    with top[1]:
        field_card("材料反推轮次", funding["inferred_round"])
    with top[2]:
        field_card("判断置信度", RISK_LABELS.get(funding["round_confidence"], funding["round_confidence"]))

    st.markdown("#### 轮次质量判断")
    cols = st.columns(2)
    with cols[0]:
        st.write(f"资料充分度：{funding['material_sufficiency']}")
        st.write(f"风险收益特征：{funding['risk_return_profile']}")
        st.write(f"估值/阶段匹配：{funding['valuation_fit']}")
    with cols[1]:
        st.write(f"稳定性判断：{funding['stability_assessment']}")
        st.write(f"回款周期判断：{funding['payback_cycle_view']}")
        st.write(f"仍需核验：{funding['missing_round_evidence']}")

    st.markdown("#### 投资人信号")
    st.write(funding["investor_signal"])
    try:
        investors = json.loads(funding["existing_investors"] or "[]")
    except json.JSONDecodeError:
        investors = []
    if investors:
        st.dataframe(
            [
                {
                    "投资人": item.get("name", ""),
                    "类型": item.get("investor_type", ""),
                    "轮次": item.get("round", ""),
                    "信号强度": item.get("signal_strength", ""),
                    "意义": item.get("why_it_matters", ""),
                    "需核验": item.get("needs_verification", ""),
                }
                for item in investors
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("BP 未披露历史投资人、领投方或跟投方。")

    st.caption(f"可选核验方式：{funding['suggested_checks']}")


def risk_sort_value(task: Dict[str, object]) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(task["risk_level"]), 3)


def render_task_cards(tasks: List[Dict[str, object]], empty_text: str, assumption_by_id: Optional[Dict[str, Dict[str, object]]] = None) -> None:
    if not tasks:
        st.info(empty_text)
        return

    for task in tasks:
        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(f"**{task['title']}**")
                if assumption_by_id is not None:
                    linked_question = assumption_by_id.get(task.get("linked_assumption_id"), {})
                    st.caption(f"关联研究问题：{linked_question.get('assumption_text', '未关联研究问题')}")
                st.caption(f"已有证据：{task['existing_evidence']}")
            with cols[1]:
                st.write(f"待核验强度：{RISK_LABELS.get(task['risk_level'], task['risk_level'])}")
            with cols[2]:
                st.write(f"状态：{STATUS_LABELS.get(task['status'], task['status'])}")

            st.write(f"缺失证据：{task['missing_evidence']}")
            st.write(f"可请求材料：{task['suggested_materials']}")
            st.write(f"可访谈对象：{task['suggested_interviewees']}")
            st.caption(f"问创始人：{task['founder_questions']}")
            st.caption(f"问客户：{task['customer_questions']}")

            with st.form(f"task_{task['id']}"):
                status = st.selectbox(
                    "状态",
                    list(STATUS_LABELS),
                    index=list(STATUS_LABELS).index(task["status"]),
                    format_func=lambda value: STATUS_LABELS[value],
                )
                risk = st.selectbox(
                    "风险",
                    list(RISK_LABELS),
                    index=list(RISK_LABELS).index(task["risk_level"]),
                    format_func=lambda value: RISK_LABELS[value],
                )
                notes = st.text_input("备注", value=task["user_notes"])
                if st.form_submit_button("保存任务状态"):
                    update_task(task["id"], status, risk, notes)
                    st.success("已更新")
                    st.rerun()


def tasks_tab(bundle: Dict[str, object]) -> None:
    st.subheader("核验计划")
    assumption_by_id = {item.get("id"): item for item in bundle.get("assumptions", [])}
    with st.expander("添加核验计划"):
        with st.form(f"manual_task_{bundle['project']['id']}"):
            title = st.text_input("任务标题", placeholder="例如：验证核心客户是否真实续费")
            task_type = st.selectbox(
                "任务类型",
                [
                    "demand",
                    "market",
                    "growth",
                    "business_model",
                    "team",
                    "moat",
                    "financial_quality",
                    "financing_use",
                ],
                format_func=lambda value: {
                    "demand": "需求",
                    "market": "市场",
                    "growth": "增长",
                    "business_model": "商业模式",
                    "team": "团队",
                    "moat": "技术 / 壁垒",
                    "financial_quality": "财务质量",
                    "financing_use": "融资用途",
                }[value],
            )
            risk_level = st.selectbox("待核验风险强度", list(RISK_LABELS), format_func=lambda value: RISK_LABELS[value])
            existing_evidence = st.text_area("当前已有证据", placeholder="用户观察到的线索、BP 中对应描述或外部资料")
            missing_evidence = st.text_area("缺失证据", placeholder="还需要哪些材料或数据")
            suggested_materials = st.text_input("可请求材料", placeholder="客户合同、回款记录、访谈纪要")
            suggested_interviewees = st.text_input("可访谈对象", placeholder="创始人、客户负责人、财务负责人")
            founder_questions = st.text_area("问创始人的问题", placeholder="希望创始人澄清什么")
            customer_questions = st.text_area("问客户的问题", placeholder="希望客户验证什么")
            user_notes = st.text_input("备注")
            if st.form_submit_button("添加核验计划", type="primary"):
                if not title.strip() or not missing_evidence.strip():
                    st.warning("请至少填写任务标题和缺失证据。")
                else:
                    create_manual_task(
                        bundle["project"]["id"],
                        title,
                        task_type,
                        risk_level,
                        existing_evidence,
                        missing_evidence,
                        suggested_materials,
                        suggested_interviewees,
                        founder_questions,
                        customer_questions,
                        user_notes,
                    )
                    st.success("已添加核验计划")
                    st.rerun()

    if not bundle["tasks"]:
        st.info("上传 BP 后，研究问题会自动整理成核验计划。")
        return

    pending_tasks = sorted(
        [task for task in bundle["tasks"] if task["status"] != "verified"],
        key=lambda task: (risk_sort_value(task), task["updated_at"]),
    )
    verified_tasks = sorted(
        [task for task in bundle["tasks"] if task["status"] == "verified"],
        key=lambda task: task["updated_at"],
        reverse=True,
    )
    pending_tab, verified_tab = st.tabs([f"未完成（{len(pending_tasks)}）", f"已完成（{len(verified_tasks)}）"])
    with pending_tab:
        render_task_cards(pending_tasks, "暂无待处理核验计划。", assumption_by_id)
    with verified_tab:
        render_task_cards(verified_tasks, "暂无已完成人工核验动作。", assumption_by_id)


def render_execution_plans(bundle: Dict[str, object]) -> None:
    st.subheader("核验计划")
    assumption_by_id = {item.get("id"): item for item in bundle.get("assumptions", [])}
    tasks = sorted(
        bundle.get("tasks", []),
        key=lambda task: (task.get("status") == "verified", risk_sort_value(task), task.get("updated_at", "")),
    )
    if not tasks:
        st.info("暂无核验计划。请先到「问题核验」为研究问题添加核验计划。")
        return
    for task in tasks:
        with st.container(border=True):
            linked_question = assumption_by_id.get(task.get("linked_assumption_id"), {})
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(f"**{task['title']}**")
                st.caption(f"关联研究问题：{linked_question.get('assumption_text', '未关联研究问题')}")
            with cols[1]:
                st.write(f"待核验强度：{RISK_LABELS.get(task['risk_level'], task['risk_level'])}")
            with cols[2]:
                st.write(f"状态：{STATUS_LABELS.get(task['status'], task['status'])}")
            st.write(f"缺失证据：{task['missing_evidence']}")
            st.write(f"建议材料：{task['suggested_materials']}")
            st.write(f"建议访谈对象：{task['suggested_interviewees']}")
            st.caption(f"问创始人：{task['founder_questions']}")
            st.caption(f"问客户：{task['customer_questions']}")
            with st.form(f"execution_plan_{task['id']}"):
                status = st.selectbox(
                    "状态",
                    list(STATUS_LABELS),
                    index=list(STATUS_LABELS).index(task["status"]),
                    format_func=lambda value: STATUS_LABELS[value],
                    key=f"execution_status_{task['id']}",
                )
                risk = st.selectbox(
                    "待核验强度",
                    list(RISK_LABELS),
                    index=list(RISK_LABELS).index(task["risk_level"]),
                    format_func=lambda value: RISK_LABELS[value],
                    key=f"execution_risk_{task['id']}",
                )
                notes = st.text_input("人工备注", value=task["user_notes"], key=f"execution_note_{task['id']}")
                if st.form_submit_button("保存计划状态"):
                    update_task(task["id"], status, risk, notes)
                    st.success("已更新")
                    st.rerun()


def supplementary_tab(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("补充材料上传与验证")
    with st.form(f"upload_supp_{project_id}"):
        uploaded = st.file_uploader("补充材料", type=["txt", "md", "csv", "xlsx", "pdf", "docx", "pptx"], key=f"supp_file_{project_id}")
        pasted = st.text_area("或粘贴补充材料正文", height=160)
        submitted = st.form_submit_button("上传并调用 AI 验证", type="primary")
        if submitted:
            if not uploaded and not pasted.strip():
                st.warning("请上传补充材料或粘贴正文。")
                return
            try:
                with st.spinner("正在匹配历史核验计划和待核验风险..."):
                    verify_supplementary(
                        project_id,
                        uploaded.name if uploaded else "pasted-supplementary.txt",
                        uploaded_bytes(uploaded),
                        pasted,
                        LLMClient(),
                    )
                st.success("补充材料验证完成")
                st.rerun()
            except (LLMConfigError, LLMResponseError, AppError, Exception) as exc:
                st.error(str(exc))

    st.markdown("#### 证据链接")
    if bundle["evidence"]:
        st.dataframe(
            [
                {
                    "判断": EVIDENCE_JUDGMENT_LABELS.get(item["judgment"], item["judgment"]),
                    "置信度": item["confidence"],
                    "证据": item["evidence_text"],
                    "任务ID": item["task_id"],
                }
                for item in bundle["evidence"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("上传补充材料并完成验证后显示证据链接。")

    st.markdown("#### 补充材料解决问题汇总")
    if bundle.get("supplementary_resolutions"):
        st.dataframe(
            [
                {
                    "对象": item["target_title"] or item["target_type"],
                    "状态": RESOLUTION_STATUS_LABELS.get(item["resolution_status"], item["resolution_status"]),
                    "证据": item["evidence_text"],
                    "影响": item["impact_summary"],
                    "仍缺": item["remaining_gap"],
                }
                for item in bundle["supplementary_resolutions"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无补充材料解决问题汇总。")


def financial_tab(bundle: Dict[str, object]) -> None:
    st.subheader("财务分析")
    if not bundle.get("financial_analyses"):
        st.info("上传财务信息、收入明细、回款记录、成本费用或现金流材料后显示财务分析。")
        return

    for item in bundle["financial_analyses"]:
        with st.container(border=True):
            st.markdown(f"**{item['summary']}**")
            st.write(f"收入质量：{item['revenue_quality']}")
            st.write(f"毛利 / 成本费用：{item['margin_costs']}")
            st.write(f"现金流 / 回款：{item['cashflow_quality']}")
            st.write(f"客户集中：{item['customer_concentration']}")
            st.write(f"异常波动：{item['anomalies']}")
            st.write(f"与 BP 冲突：{item['bp_conflicts']}")
            st.caption(f"可请求材料：{item['follow_up_materials']}")


def memo_tab(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("Memo 草稿")
    if bundle["claims"] or bundle["highlights"] or bundle["assumptions"] or bundle["tasks"]:
        content = memo_from_bundle(bundle)
        st.download_button("下载 Markdown 草稿", content, file_name="investment_memo_draft.md", mime="text/markdown")
        st.markdown("#### Memo 草稿预览")
        st.markdown(content)
    elif bundle["memos"]:
        latest = bundle["memos"][-1]
        st.download_button("下载 Markdown 草稿", latest["content_markdown"], file_name="investment_memo_draft.md", mime="text/markdown")
        st.markdown("#### Memo 草稿预览")
        st.markdown(latest["content_markdown"])
    else:
        st.info("完成 BP 分析后，这里会自动展示 memo 草稿。")


def render_bp_upload_form(project_id: str, bundle: Dict[str, object]) -> None:
    has_bp_analysis = bool(bundle["claims"] or bundle["highlights"] or bundle["assumptions"])
    st.markdown("#### BP / 基础材料上传")
    if has_bp_analysis:
        st.caption("新版 BP、业务补充说明、会影响项目基本判断的材料放这里。")
    else:
        st.caption("可一次上传多个 BP 文件，也可以直接粘贴正文。")
    with st.form(f"upload_bp_{project_id}"):
        uploaded_files = st.file_uploader(
            "BP 文件",
            type=["txt", "md", "csv", "xlsx", "pdf", "docx", "pptx"],
            accept_multiple_files=True,
        )
        pasted = st.text_area("或粘贴 BP 正文 / 追加说明", height=180)
        submitted = st.form_submit_button("上传并调用 AI 分析" if not has_bp_analysis else "用现有和新增基础材料重新分析", type="primary")
        if submitted:
            uploads = [{"name": file.name, "content": uploaded_bytes(file)} for file in (uploaded_files or [])]
            if not uploads and not pasted.strip() and not has_bp_analysis:
                st.warning("请至少上传一个 BP 文件或粘贴 BP 正文。")
                return
            if not uploads and not pasted.strip() and has_bp_analysis:
                st.info("未添加新材料，将基于现有 BP / 基础材料重新分析。")
            try:
                with st.spinner("正在解析材料并调用 AI 综合分析..."):
                    analyze_bp_batch(
                        project_id,
                        uploads,
                        pasted,
                        include_existing=has_bp_analysis,
                        llm=LLMClient(),
                    )
                st.success("BP 综合分析完成")
                st.rerun()
            except (LLMConfigError, LLMResponseError, AppError, Exception) as exc:
                st.error(str(exc))


def render_supplementary_upload_form(project_id: str) -> None:
    st.markdown("#### 补充材料上传")
    st.caption("合同、访谈纪要、财务明细、回款记录等尽调证据放这里。解析后请到「问题核验」查看材料对研究问题的影响。")
    with st.form(f"upload_supp_{project_id}"):
        uploaded = st.file_uploader("补充材料", type=["txt", "md", "csv", "xlsx", "pdf", "docx", "pptx"], key=f"supp_file_{project_id}")
        pasted = st.text_area("或粘贴补充材料正文", height=160)
        submitted = st.form_submit_button("上传并调用 AI 验证", type="primary")
        if submitted:
            if not uploaded and not pasted.strip():
                st.warning("请上传补充材料或粘贴正文。")
                return
            try:
                with st.spinner("正在匹配历史核验计划和待核验风险..."):
                    verify_supplementary(
                        project_id,
                        uploaded.name if uploaded else "pasted-supplementary.txt",
                        uploaded_bytes(uploaded),
                        pasted,
                        LLMClient(),
                    )
                st.success("补充材料已解析，请到「问题核验」查看材料对研究问题的影响。")
                st.rerun()
            except (LLMConfigError, LLMResponseError, AppError, Exception) as exc:
                st.error(str(exc))


def render_documents_section(bundle: Dict[str, object]) -> None:
    st.markdown("#### 已上传材料")
    documents = bundle.get("documents", [])
    if documents:
        for document in documents:
            with st.container(border=True):
                cols = st.columns([2, 1, 1, 1])
                with cols[0]:
                    st.markdown(f"**{document['file_name']}**")
                with cols[1]:
                    st.caption(f"类型：{DOCUMENT_TYPE_LABELS.get(document['document_type'], document['document_type'])}")
                with cols[2]:
                    st.caption(f"状态：{DOCUMENT_STATUS_LABELS.get(document['parse_status'], document['parse_status'])}")
                with cols[3]:
                    st.caption(f"时间：{document.get('created_at', '')}")
                st.write(document["summary"] or "暂无摘要")
    else:
        st.info("暂无已上传材料。")


def render_highlights_section(bundle: Dict[str, object], limit: Optional[int] = None, title: str = "初步亮点") -> None:
    st.markdown(f"#### {title}")
    highlights = bundle.get("highlights", [])
    if limit:
        highlights = highlights[:limit]
    if highlights:
        for item in highlights:
            with st.container(border=True):
                st.markdown(f"**{item['title']}**")
                st.write(item["why_important"])
                st.caption(
                    f"对应说法：{item['linked_claim_text']}｜来源 p{item['source_page']}｜证据支撑：{item['evidence_level']}｜验证方向：{item['verification_direction']}"
                )
    else:
        st.info("上传 BP 并完成分析后显示初步亮点。")


def render_claims_section(bundle: Dict[str, object]) -> None:
    st.markdown("#### 材料陈述")
    st.caption("从 BP / 项目材料中抽取的可追溯陈述，尚不代表已验证事实。")
    if not bundle.get("claims"):
        st.info("暂无可追溯的材料陈述。上传 BP 并完成分析后显示。")
        return
    st.dataframe(
        [
            {
                "陈述内容": item["claim_text"],
                "陈述类型": item["claim_type"],
                "主题": item["topic"],
                "核验状态": STATUS_LABELS.get(item["verification_status"], item["verification_status"]),
                "来源页": item["source_page"],
                "原文摘录": item["source_quote"],
            }
            for item in bundle["claims"]
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_assumptions_section(bundle: Dict[str, object], limit: Optional[int] = None, title: str = "待验证主线") -> None:
    st.markdown(f"#### {title}")
    assumptions = bundle.get("assumptions", [])
    if limit:
        assumptions = assumptions[:limit]
    if not assumptions:
        st.info("暂无待验证判断。完成 BP 分析后会自动整理。")
        return
    st.dataframe(
        [
            {
                "待验证主线": item["assumption_text"],
                "重要性": item["importance"],
                "风险": RISK_LABELS.get(item["risk_level"], item["risk_level"]),
                "状态": STATUS_LABELS.get(item["current_status"], item["current_status"]),
                "验证方法": item["verification_method"],
                "不成立影响": item["failure_impact"],
            }
            for item in assumptions
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_material_requests_section(project_id: str, bundle: Dict[str, object]) -> None:
    st.markdown("#### 资料请求")
    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("从研究问题生成资料请求草稿", key=f"draft_materials_{project_id}"):
            drafts = generate_material_request_draft(project_id)
            if drafts:
                st.success(f"已生成 {len(drafts)} 条资料请求草稿。")
            else:
                st.info("当前研究问题对应的资料请求已存在，没有新增条目。")
            st.rerun()
    with cols[1]:
        with st.expander("手动添加资料需求", expanded=False):
            with st.form(f"manual_material_{project_id}"):
                material_name = st.text_input("资料名称")
                why_needed = st.text_area("为什么需要")
                priority = st.selectbox("优先级", ["high", "medium", "low"], format_func=lambda value: RISK_LABELS.get(value, value))
                if st.form_submit_button("添加"):
                    if not material_name.strip() or not why_needed.strip():
                        st.warning("请填写资料名称和需要原因。")
                    else:
                        create_material_request(project_id, material_name, why_needed, priority, created_by="human")
                        st.success("已添加资料需求。")
                        st.rerun()
    if bundle.get("material_requests"):
        for item in bundle["material_requests"]:
            with st.container(border=True):
                st.markdown(f"**{item['material_name']}**")
                st.caption(f"优先级：{RISK_LABELS.get(item['priority'], item['priority'])}｜来源：{MATERIAL_SOURCE_LABELS.get(item['created_by'], item['created_by'])}｜状态：{MATERIAL_REQUEST_STATUS_LABELS.get(item['status'], item['status'])}")
                st.write(item["why_needed"])
                cols = st.columns([1, 2])
                with cols[0]:
                    next_status = st.selectbox(
                        "更新状态",
                        list(MATERIAL_REQUEST_STATUS_LABELS),
                        index=list(MATERIAL_REQUEST_STATUS_LABELS).index(item["status"]) if item["status"] in MATERIAL_REQUEST_STATUS_LABELS else 0,
                        format_func=lambda value: MATERIAL_REQUEST_STATUS_LABELS[value],
                        key=f"mat_status_{item['id']}",
                    )
                with cols[1]:
                    note = st.text_input("人工备注", value=item.get("human_note") or "", key=f"mat_note_{item['id']}")
                if st.button("保存资料状态", key=f"mat_save_{item['id']}"):
                    update_material_request_status(item["id"], next_status, note)
                    st.rerun()
    else:
        st.info("暂无资料请求。")


def render_interview_notes_section(project_id: str, bundle: Dict[str, object]) -> None:
    st.markdown("#### 访谈纪要")
    with st.form(f"interview_note_{project_id}"):
        cols = st.columns(4)
        with cols[0]:
            interview_type = st.selectbox("访谈类型", list(INTERVIEW_TYPE_LABELS), format_func=lambda value: INTERVIEW_TYPE_LABELS[value])
        with cols[1]:
            interviewee_name = st.text_input("访谈对象")
        with cols[2]:
            interviewee_role = st.text_input("角色")
        with cols[3]:
            organization = st.text_input("机构")
        interview_date = st.text_input("访谈日期", placeholder="YYYY-MM-DD")
        raw_note = st.text_area("纪要原文")
        if st.form_submit_button("保存纪要并生成 AI 待确认提示"):
            if raw_note.strip():
                note_id = insert_interview_note(
                    project_id,
                    interview_type,
                    raw_note,
                    interviewee_name,
                    interviewee_role,
                    organization,
                    interview_date,
                    st.session_state.get("display_name", "本地研究员"),
                )
                analyze_interview_note(project_id, note_id)
                st.success("纪要已保存，并生成待确认 AI 提示。")
                st.rerun()
            else:
                st.warning("请填写纪要原文。")
    if bundle.get("interview_notes"):
        st.dataframe(
            [
                {
                    "类型": INTERVIEW_TYPE_LABELS.get(item["interview_type"], item["interview_type"]),
                    "对象": item["interviewee_name"],
                    "角色": item["interviewee_role"],
                    "机构": item["organization"],
                    "日期": item["interview_date"],
                    "摘要": item["summary"],
                    "时间": item["created_at"],
                }
                for item in bundle["interview_notes"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无访谈纪要。")


def render_project_overview(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("项目总览")
    project = bundle["project"]
    info_cols = st.columns(4)
    with info_cols[0]:
        field_card("公司", project["company_name"])
    with info_cols[1]:
        field_card("行业", project["industry"])
    with info_cols[2]:
        field_card("融资阶段", project["financing_stage"])
    with info_cols[3]:
        field_card("项目阶段", HUMAN_PROJECT_STATUS_LABELS.get(project.get("human_project_status"), project.get("human_project_status")))
    st.caption("一句话介绍")
    st.markdown(f"**{project['one_liner'] or '待确认'}**")

    status_cols = st.columns(5)
    with status_cols[0]:
        field_card("材料阶段", MATERIAL_STAGE_LABELS.get(project.get("material_stage"), project.get("material_stage")))
    with status_cols[1]:
        field_card("材料成熟度", JUDGEMENT_READINESS_LABELS.get(project.get("judgement_readiness"), project.get("judgement_readiness")))
    with status_cols[2]:
        field_card("材料分析进度", AI_RESEARCH_STATE_LABELS.get(project.get("ai_research_state"), project.get("ai_research_state")))
    with status_cols[3]:
        strategy_status = project.get("strategy_match_status", "unknown_due_to_missing_materials")
        field_card("策略匹配", STRATEGY_MATCH_LABELS.get(strategy_status, strategy_status))
    with status_cols[4]:
        field_card("待确认 AI 更新", project.get("pending_ai_suggestion_count", project.get("pending_ai_updates_count", 0)))

    render_highlights_section(bundle, limit=3, title="初步亮点 Top 3")

    st.markdown("#### 关键研究问题")
    assumptions = top_unverified_assumptions(bundle)
    if assumptions:
        for item in assumptions:
            with st.container(border=True):
                st.markdown(f"**{item['assumption_text']}**")
                st.caption(f"风险：{RISK_LABELS.get(item['risk_level'], item['risk_level'])}｜状态：{STATUS_LABELS.get(item['current_status'], item['current_status'])}")
                st.write(item["verification_method"])
    else:
        st.info("暂无研究问题。")

    st.markdown("#### 待核验风险 Top 3")
    risks = top_open_risks(bundle)
    if risks:
        for risk in risks:
            with st.container(border=True):
                st.markdown(f"**{risk['title']}**")
                st.caption(f"类型：{risk['category']}｜严重度：{risk['severity']}｜状态：{risk['status']}")
                st.write(risk["description"])
    else:
        st.info("暂无待核验风险。")

    st.markdown("#### 下一步尽调动作 Top 3")
    tasks = top_open_tasks(bundle)
    if tasks:
        for task in tasks:
            with st.container(border=True):
                st.markdown(f"**{task['title']}**")
                st.caption(f"风险：{RISK_LABELS.get(task['risk_level'], task['risk_level'])}｜状态：{STATUS_LABELS.get(task['status'], task['status'])}")
                st.write(task["missing_evidence"])
    else:
        st.info("暂无下一步尽调动作。")


def render_material_center(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("材料中心")
    project = bundle["project"]
    cols = st.columns(4)
    with cols[0]:
        field_card("材料阶段", MATERIAL_STAGE_LABELS.get(project.get("material_stage"), project.get("material_stage")))
    with cols[1]:
        field_card("材料成熟度", JUDGEMENT_READINESS_LABELS.get(project.get("judgement_readiness"), project.get("judgement_readiness")))
    with cols[2]:
        field_card("材料分析进度", AI_RESEARCH_STATE_LABELS.get(project.get("ai_research_state"), project.get("ai_research_state")))
    with cols[3]:
        field_card("文档数量", len(bundle.get("documents", [])))

    render_bp_upload_form(project_id, bundle)
    st.divider()
    render_supplementary_upload_form(project_id)
    st.divider()
    render_documents_section(bundle)

    st.markdown("#### 材料覆盖度摘要")
    scorecards = [
        {
            "维度": item["dimension"],
            "等级": EVIDENCE_SUFFICIENCY_LABELS.get(item["level"], item["level"]),
            "说明": item["explanation"],
            "证据等级": EVIDENCE_SUFFICIENCY_LABELS.get(item.get("evidence_level", ""), item.get("evidence_level", "")),
        }
        for item in bundle.get("readiness_scorecards", [])
    ]
    if scorecards:
        st.dataframe(scorecards, use_container_width=True, hide_index=True)
    else:
        st.info("暂无材料覆盖度评分。上传并分析材料后显示。")

    pending_requests = [item for item in bundle.get("material_requests", []) if item.get("status") not in {"received", "waived"}]
    st.markdown("#### 待索取资料提示")
    if pending_requests:
        st.dataframe(
            [
                {
                    "资料": item["material_name"],
                    "优先级": RISK_LABELS.get(item["priority"], item["priority"]),
                    "状态": MATERIAL_REQUEST_STATUS_LABELS.get(item["status"], item["status"]),
                    "为什么需要": item["why_needed"],
                }
                for item in pending_requests
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("资料状态请到“尽调执行”更新。")
    else:
        st.info("暂无待索取资料。")


def render_project_breakdown(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("项目拆解")
    st.caption("本页只回答“这家公司是什么”：业务、赛道、产品、客户、财务、团队和轮次。需要验证的问题请到「问题核验」查看。")
    render_claims_section(bundle)
    render_highlights_section(bundle)
    with st.expander("市场与竞争", expanded=True):
        sector_tab(project_id, bundle)
    with st.expander("客户与需求", expanded=True):
        render_claim_subset_section("客户与需求", bundle, ["客户", "需求", "续费", "回款", "药房"])
    with st.expander("产品与技术", expanded=True):
        render_claim_subset_section("产品与技术", bundle, ["产品", "技术", "AI", "系统", "平台", "算法"])
    with st.expander("商业化与财务", expanded=True):
        financial_tab(bundle)
        render_claim_subset_section("商业化陈述", bundle, ["收入", "毛利", "成本", "费用", "现金流", "商业化"])
    with st.expander("团队与治理", expanded=True):
        render_claim_subset_section("团队与治理", bundle, ["团队", "创始", "管理", "治理", "股权"])
    with st.expander("轮次与交易结构", expanded=True):
        funding_tab(bundle)
    st.info("需要验证的问题请到「问题核验」查看。")


def render_question_verification(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("问题核验")
    st.caption("这里把 BP 初读形成的研究问题、当前材料的回答、证据缺口和下一步尽调动作放在同一条线上。AI 不做投资结论，只帮助整理问题和证据。")
    render_manual_research_question_form(project_id)
    render_pending_ai_suggestions(project_id)

    threads = build_question_threads(bundle)
    if not threads:
        st.info("暂无研究问题。可先添加研究问题，或上传 BP 后由 AI 初读整理。")
        return

    st.markdown("#### 研究问题总表")
    st.dataframe(question_thread_summary_rows(threads), use_container_width=True, hide_index=True)

    options = {
        str(thread["assumption"].get("assumption_text", ""))[:80]: index
        for index, thread in enumerate(threads)
    }
    selected_label = st.selectbox("查看研究问题详情", list(options), key=f"question_thread_select_{project_id}")
    thread = threads[options[selected_label]]
    assumption = thread["assumption"]
    linked_tasks = thread["tasks"]
    linked_evidence = thread["evidence"]
    answer_state = thread["answer_state"]

    st.markdown("#### 为什么问")
    with st.container(border=True):
        st.markdown(f"**{assumption.get('assumption_text', '')}**")
        st.write(f"为什么重要：{assumption.get('why_it_matters') or assumption.get('importance', '')}")
        st.write(f"失败影响：{assumption.get('failure_impact', '')}")
        st.write(f"验证方法：{assumption.get('verification_method', '')}")
        related_claims = [
            claim for claim in bundle.get("claims", [])
            if any(str(task.get("linked_claim_id")) == str(claim.get("id")) for task in linked_tasks)
        ]
        if related_claims:
            st.caption("相关材料陈述")
            st.dataframe(
                [
                    {
                        "陈述内容": item["claim_text"],
                        "来源页": item["source_page"],
                        "原文摘录": item["source_quote"],
                    }
                    for item in related_claims
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("暂未找到明确关联的材料陈述。")

    st.markdown("#### 当前材料怎么回答")
    with st.container(border=True):
        st.write(f"当前材料回答：{answer_state['answer']}")
        if linked_evidence:
            st.write("AI 基于已上传补充材料给出了过程性证据判断。")
        else:
            st.write("当前只来自 BP 初读和材料陈述，尚无补充材料证据。")
        st.caption("这不是投资结论，只是材料层面的回答。")

    st.markdown("#### 证据与缺口")
    if linked_evidence:
        st.dataframe(
            [
                {
                    "证据": item["evidence_text"],
                    "判断": EVIDENCE_JUDGMENT_LABELS.get(item["judgment"], item["judgment"]),
                    "置信度": item["confidence"],
                    "document_id": item["document_id"],
                    "chunk_id": item["chunk_id"],
                }
                for item in linked_evidence
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无补充材料证据。")
    missing_rows = [
        {
            "核验计划": task["title"],
            "仍缺证据": task["missing_evidence"],
            "建议材料": task["suggested_materials"],
        }
        for task in linked_tasks
        if task.get("status") != "verified"
    ]
    if missing_rows:
        st.dataframe(missing_rows, use_container_width=True, hide_index=True)

    st.markdown("#### 下一步尽调")
    if linked_tasks:
        st.dataframe(
            [
                {
                    "核验计划": task["title"],
                    "缺失证据": task["missing_evidence"],
                    "建议材料": task["suggested_materials"],
                    "建议访谈对象": task["suggested_interviewees"],
                    "问创始人": task["founder_questions"],
                    "问客户": task["customer_questions"],
                    "状态": STATUS_LABELS.get(task["status"], task["status"]),
                }
                for task in linked_tasks
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("该研究问题下暂无核验计划。")

    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button("生成资料请求草稿", key=f"question_materials_{assumption.get('id')}"):
            drafts = generate_material_request_draft(project_id)
            if drafts:
                st.success(f"已生成 {len(drafts)} 条资料请求草稿。")
            else:
                st.info("当前研究问题相关资料请求已存在，没有新增条目。")
            st.rerun()
    with action_cols[1]:
        with st.expander("＋ 添加核验计划", expanded=False):
            with st.form(f"manual_question_task_{assumption.get('id')}"):
                title = st.text_input("核验计划标题", placeholder="例如：核验核心客户回款是否真实")
                existing_evidence = st.text_area("当前已有证据")
                missing_evidence = st.text_area("缺失证据")
                suggested_materials = st.text_input("建议材料")
                suggested_interviewees = st.text_input("建议访谈对象")
                founder_questions = st.text_area("问创始人的问题")
                customer_questions = st.text_area("问客户的问题")
                risk_level = st.selectbox("待核验强度", list(RISK_LABELS), format_func=lambda value: RISK_LABELS[value])
                user_notes = st.text_input("备注")
                if st.form_submit_button("添加核验计划"):
                    if not title.strip() or not missing_evidence.strip():
                        st.warning("请至少填写核验计划标题和缺失证据。")
                    else:
                        create_manual_task(
                            project_id,
                            title,
                            "manual",
                            risk_level,
                            existing_evidence,
                            missing_evidence,
                            suggested_materials,
                            suggested_interviewees,
                            founder_questions,
                            customer_questions,
                            user_notes,
                            linked_assumption_id=str(assumption.get("id", "")),
                        )
                        st.success("已添加核验计划。")
                        st.rerun()

    unlinked_tasks = [task for task in bundle.get("tasks", []) if not task.get("linked_assumption_id")]
    if unlinked_tasks:
        with st.expander("未关联核验计划", expanded=False):
            st.dataframe(
                [
                    {
                        "核验计划": task["title"],
                        "缺失证据": task["missing_evidence"],
                        "状态": STATUS_LABELS.get(task["status"], task["status"]),
                    }
                    for task in unlinked_tasks
                ],
                use_container_width=True,
                hide_index=True,
            )

    if bundle.get("material_requests"):
        with st.expander("未关联资料请求", expanded=False):
            st.dataframe(
                [
                    {
                        "资料": item["material_name"],
                        "状态": MATERIAL_REQUEST_STATUS_LABELS.get(item["status"], item["status"]),
                        "为什么需要": item["why_needed"],
                    }
                    for item in bundle["material_requests"]
                ],
                use_container_width=True,
                hide_index=True,
            )

    open_flags = build_red_flag_rows(bundle)
    if open_flags:
        with st.expander("全局待核验风险", expanded=False):
            st.dataframe(
                [
                    {
                        "关联对象": item["related_object"],
                        "风险": item["title"],
                        "状态": item["status"],
                        "依据": item["evidence"],
                        "核验方式": item["suggested_verification"],
                    }
                    for item in open_flags
                ],
                use_container_width=True,
                hide_index=True,
            )


def render_dd_execution(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("尽调执行")
    st.caption("这里只管理执行动作。问题本身、当前回答和证据判断请到「问题核验」查看。")
    render_execution_plans(bundle)
    st.divider()
    render_material_requests_section(project_id, bundle)
    st.divider()
    render_interview_notes_section(project_id, bundle)


def render_memo_and_records(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("Memo 与记录")
    st.markdown("#### Memo 分节草稿")
    if st.button("生成 / 刷新 Memo 草稿", key=f"refresh_memo_sections_{project_id}"):
        generate_memo_from_data(project_id)
        st.success("Memo 草稿已刷新。")
        st.rerun()
    if bundle.get("memo_sections"):
        for section in bundle["memo_sections"]:
            with st.expander(section["section_title"], expanded=False):
                st.markdown(section["ai_draft"] or "暂无草稿内容。")
    else:
        st.info("暂无 Memo 分节草稿。")

    content = memo_from_bundle(bundle)
    if content.strip():
        st.download_button("下载完整 Markdown 草稿", content, file_name="investment_memo_draft.md", mime="text/markdown")
        with st.expander("完整草稿预览", expanded=False):
            st.markdown(content)

    st.divider()
    st.markdown("#### 人工项目阶段与记录")
    project = bundle["project"]
    with st.form(f"human_status_{project_id}"):
        status_keys = list(HUMAN_PROJECT_STATUS_LABELS)
        current_status = project.get("human_project_status") or "inbox"
        new_status = st.selectbox(
            "项目阶段",
            status_keys,
            index=status_keys.index(current_status) if current_status in status_keys else 0,
            format_func=lambda value: HUMAN_PROJECT_STATUS_LABELS[value],
            key=f"human_status_select_{project_id}",
        )
        reason_category = st.selectbox(
            "人工原因分类",
            ["材料不足，暂缓", "需要进一步访谈", "需要补充财务材料", "需要外部核验", "进入轻尽调", "进入完整尽调", "准备 memo", "提交投委会", "人工决定归档", "长期跟踪", "其他"],
            key=f"human_reason_category_{project_id}",
        )
        reason = st.text_area("人工说明", key=f"human_reason_{project_id}")
        if st.form_submit_button("保存人工记录"):
            update_human_project_status(project_id, new_status, reason, reason_category, st.session_state.get("display_name", "本地研究员"))
            st.session_state.project_id = project_id
            st.session_state.page = "项目池"
            st.session_state.last_human_status_update = {
                "project_id": project_id,
                "company_name": project["company_name"],
                "new_status": new_status,
            }
            st.rerun()
    if bundle.get("human_decision_logs"):
        st.dataframe(
            [
                {
                    "从": HUMAN_PROJECT_STATUS_LABELS.get(item["previous_status"], item["previous_status"]),
                    "到": HUMAN_PROJECT_STATUS_LABELS.get(item["new_status"], item["new_status"]),
                    "原因": item["decision_reason_category"],
                    "说明": item["decision_reason"],
                    "操作人": item["decided_by"],
                    "时间": item["created_at"],
                }
                for item in bundle["human_decision_logs"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无人工记录。")

    st.markdown("#### 项目事件")
    if bundle.get("project_events"):
        st.dataframe(
            [
                {
                    "事件": item["event_type"],
                    "摘要": item["event_summary"],
                    "来源": item["actor_type"],
                    "操作人": item["actor_name"],
                    "时间": item["created_at"],
                }
                for item in bundle["project_events"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无项目事件。")


def render_project_intake_and_strategy(project_id: str, bundle: Dict[str, object]) -> None:
    upload_bp_tab(project_id, bundle)
    st.markdown("#### 投资策略匹配")
    st.caption("策略匹配只形成过程信号，不自动改变项目状态或投资判断。")
    strategies = bundle.get("fund_strategies", [])
    if strategies:
        options = {f"{item['strategy_name']}｜{item.get('focus_sectors') or '未填赛道'}": item["id"] for item in strategies}
        selected = st.selectbox("选择基金策略", list(options), key=f"strategy_select_{project_id}")
        if st.button("检查是否符合投资策略", key=f"match_strategy_{project_id}"):
            analyze_strategy_match(project_id, options[selected])
            st.success("已生成策略匹配结果，需研究员复核。")
            st.rerun()
    else:
        st.info("暂无投资策略。请先到“投资策略”页面添加策略。")

    matches = bundle.get("project_strategy_matches", [])
    if matches:
        st.dataframe(
            [
                {
                    "结果": STRATEGY_MATCH_LABELS.get(item["match_status"], item["match_status"]),
                    "匹配项": "；".join(json_list(item["matched_items_json"])),
                    "待确认项": "；".join(json_list(item["unknown_items_json"])),
                    "范围外信号": "；".join(json_list(item["outside_scope_items_json"])),
                    "摘要": item["source_summary"],
                    "时间": item["created_at"],
                }
                for item in matches
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write(f"当前投资策略匹配：{STRATEGY_MATCH_LABELS.get(bundle['project'].get('strategy_match_status'), bundle['project'].get('strategy_match_status'))}")


def render_judgement_readiness(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("材料检查")
    project = bundle["project"]
    cols = st.columns(4)
    with cols[0]:
        field_card("材料阶段", MATERIAL_STAGE_LABELS.get(project.get("material_stage"), project.get("material_stage")))
    with cols[1]:
        field_card("判断把握", JUDGEMENT_READINESS_LABELS.get(project.get("judgement_readiness"), project.get("judgement_readiness")))
    with cols[2]:
        field_card("材料处理进度", AI_RESEARCH_STATE_LABELS.get(project.get("ai_research_state"), project.get("ai_research_state")))
    with cols[3]:
        evidence_status = project.get("evidence_sufficiency", "low")
        field_card("证据支撑", EVIDENCE_SUFFICIENCY_LABELS.get(evidence_status, evidence_status))

    st.markdown("#### 已能看到的信息")
    if bundle["claims"]:
        st.dataframe(
            [
                {
                    "陈述内容": item["claim_text"],
                    "主题": item["topic"],
                    "证据等级": EVIDENCE_SUFFICIENCY_LABELS["company_claim_only"],
                    "来源页": item["source_page"],
                    "原文摘录": item["source_quote"],
                }
                for item in bundle["claims"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无可追溯的材料陈述。上传 BP 并完成分析后显示。")

    st.markdown("#### 还缺什么")
    gaps = []
    for task in bundle["tasks"]:
        if task["status"] != "verified":
            gaps.append({"暂不能判断": task["title"], "原因": task["missing_evidence"], "需要证据": task["suggested_materials"]})
    if gaps:
        st.dataframe(gaps, use_container_width=True, hide_index=True)
    else:
        st.info("暂无系统生成的信息缺口。")

    st.markdown("#### 判断依据")
    scorecards = [
        {
            "维度": item["dimension"],
            "等级": EVIDENCE_SUFFICIENCY_LABELS.get(item["level"], item["level"]),
            "说明": item["explanation"],
            "证据等级": EVIDENCE_SUFFICIENCY_LABELS.get(item.get("evidence_level", ""), item.get("evidence_level", "")),
        }
        for item in bundle.get("readiness_scorecards", [])
    ]
    if not scorecards:
        scorecards = [
            {"维度": "材料完整度", "等级": EVIDENCE_SUFFICIENCY_LABELS.get(project.get("evidence_sufficiency", "low"), project.get("evidence_sufficiency", "low")), "说明": "基于当前上传材料数量和类型的过程性判断。", "需要补充": ""},
            {"维度": "来源可追溯性", "等级": "medium" if bundle["chunks"] else "not_assessable", "说明": "材料陈述和初步亮点已绑定来源页和原文摘录。", "需要补充": ""},
            {"维度": "核心假设覆盖度", "等级": "medium" if bundle["assumptions"] else "low", "说明": "是否形成待验证假设与动作。", "需要补充": ""},
            {"维度": "证据强度", "等级": project.get("evidence_sufficiency", "low"), "说明": "多数材料仍需区分材料陈述（未核验）和外部/原始证据。", "需要补充": ""},
            {"维度": "风险澄清度", "等级": "low" if bundle.get("red_flags") else "medium", "说明": "疑似异常和信息缺口是否已有补充材料解释。", "需要补充": ""},
            {"维度": "投资策略匹配", "等级": "not_assessable", "说明": "尚未配置投资策略。", "需要补充": "配置投资策略并检查项目是否匹配。"},
        ]
    st.dataframe(scorecards, use_container_width=True, hide_index=True)


def render_hypotheses_and_research_framework(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("项目拆解")
    bp_analysis_tab(bundle)
    st.markdown("#### 待验证判断清单")
    hypotheses = bundle.get("investment_hypotheses", [])
    if hypotheses:
        st.dataframe(
            [
                {
                    "类别": HYPOTHESIS_CATEGORY_LABELS.get(item["hypothesis_category"], item["hypothesis_category"]),
                    "假设": item["hypothesis_text"],
                    "为什么重要": item["why_it_matters"],
                    "状态": STATUS_LABELS.get(item["status"], item["status"]),
                    "证据等级": EVIDENCE_SUFFICIENCY_LABELS.get(item["evidence_level"], item["evidence_level"]),
                    "人工备注": item["human_note"],
                }
                for item in hypotheses
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无待验证判断。完成 BP 分析后会自动整理。")
    with st.expander("市场与竞争", expanded=True):
        sector_tab(project_id, bundle)
    with st.expander("轮次与交易结构", expanded=True):
        funding_tab(bundle)
    with st.expander("财务与商业化核验", expanded=True):
        financial_tab(bundle)


def render_evidence_and_risks(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("证据核验")
    st.caption("AI 发现的问题默认是信息缺口、疑似异常或待核验风险，不是确认风险。")
    red_flags_tab(bundle)
    st.markdown("#### 待核验问题")
    if bundle.get("risk_items"):
        st.dataframe(
            [
                {
                    "风险类型": item["risk_category"],
                    "标题": item["risk_title"],
                    "触发原因": item["risk_description"],
                    "严重度": RISK_LABELS.get(item["severity_candidate"], item["severity_candidate"]),
                    "状态": RISK_ITEM_STATUS_LABELS.get(item["risk_status"], item["risk_status"]),
                    "需验证": item["suggested_verification_method"],
                }
                for item in bundle["risk_items"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无待核验问题。")
    st.markdown("#### 已收集证据")
    if bundle.get("evidence_items"):
        st.dataframe(
            [
                {
                    "事实/证据": item["evidence_text"],
                    "来源类型": item["evidence_type"],
                    "证据等级": EVIDENCE_SUFFICIENCY_LABELS.get(item["evidence_level"], item["evidence_level"]),
                    "关联对象": item["related_object_type"],
                    "人工确认": "是" if item["human_verified"] else "否",
                    "来源页": item["source_page"],
                }
                for item in bundle["evidence_items"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    elif bundle["evidence"]:
        st.dataframe(
            [
                {
                    "证据": item["evidence_text"],
                    "证据等级": "company_material",
                    "AI 置信度": item["confidence"],
                    "人工确认": "否",
                    "判断": item["judgment"],
                }
                for item in bundle["evidence"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无补充材料证据链接。")


def render_dd_actions_and_interviews(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("尽调执行")
    st.caption("AI 只生成动作草稿；任务关闭和人工状态变化由研究员执行。")
    tasks_tab(bundle)
    st.markdown("#### 尽调动作")
    if bundle.get("research_actions"):
        st.dataframe(
            [
                {
                    "动作类型": RESEARCH_ACTION_TYPE_LABELS.get(item["action_type"], item["action_type"]),
                    "动作": item["title"],
                    "目标": item["linked_hypothesis_id"] or item["linked_risk_id"],
                    "优先级": item["priority"],
                    "状态": ACTION_STATUS_LABELS.get(item["action_status"], item["action_status"]),
                    "说明": item["description"],
                }
                for item in bundle["research_actions"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无尽调动作。")
    st.divider()
    st.markdown("#### 资料清单")
    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("从待核验事项生成资料清单草稿", key=f"draft_materials_{project_id}"):
            drafts = generate_material_request_draft(project_id)
            if drafts:
                st.success(f"已生成 {len(drafts)} 条资料清单草稿。")
            else:
                st.info("当前待核验事项对应的资料清单已存在，没有新增条目。")
            st.rerun()
    with cols[1]:
        with st.expander("手动添加资料需求", expanded=False):
            with st.form(f"manual_material_{project_id}"):
                material_name = st.text_input("资料名称")
                why_needed = st.text_area("为什么需要")
                priority = st.selectbox("优先级", ["high", "medium", "low"], format_func=lambda value: RISK_LABELS.get(value, value))
                if st.form_submit_button("添加"):
                    if not material_name.strip() or not why_needed.strip():
                        st.warning("请填写资料名称和需要原因。")
                    else:
                        create_material_request(project_id, material_name, why_needed, priority, created_by="human")
                        st.success("已添加资料需求。")
                        st.rerun()
    if bundle.get("material_requests"):
        for item in bundle["material_requests"]:
            with st.container(border=True):
                st.markdown(f"**{item['material_name']}**")
                st.caption(f"优先级：{RISK_LABELS.get(item['priority'], item['priority'])}｜来源：{MATERIAL_SOURCE_LABELS.get(item['created_by'], item['created_by'])}｜状态：{MATERIAL_REQUEST_STATUS_LABELS.get(item['status'], item['status'])}")
                st.write(item["why_needed"])
                cols = st.columns([1, 2])
                with cols[0]:
                    next_status = st.selectbox(
                        "更新状态",
                        list(MATERIAL_REQUEST_STATUS_LABELS),
                        index=list(MATERIAL_REQUEST_STATUS_LABELS).index(item["status"]) if item["status"] in MATERIAL_REQUEST_STATUS_LABELS else 0,
                        format_func=lambda value: MATERIAL_REQUEST_STATUS_LABELS[value],
                        key=f"mat_status_{item['id']}",
                    )
                with cols[1]:
                    note = st.text_input("人工备注", value=item.get("human_note") or "", key=f"mat_note_{item['id']}")
                if st.button("保存资料状态", key=f"mat_save_{item['id']}"):
                    update_material_request_status(item["id"], next_status, note)
                    st.rerun()
    else:
        st.info("暂无资料清单。")
    st.divider()
    supplementary_tab(project_id, bundle)
    st.divider()
    st.markdown("#### 访谈纪要")
    with st.form(f"interview_note_{project_id}"):
        cols = st.columns(4)
        with cols[0]:
            interview_type = st.selectbox("访谈类型", list(INTERVIEW_TYPE_LABELS), format_func=lambda value: INTERVIEW_TYPE_LABELS[value])
        with cols[1]:
            interviewee_name = st.text_input("访谈对象")
        with cols[2]:
            interviewee_role = st.text_input("角色")
        with cols[3]:
            organization = st.text_input("机构")
        interview_date = st.text_input("访谈日期", placeholder="YYYY-MM-DD")
        raw_note = st.text_area("纪要原文")
        if st.form_submit_button("保存纪要并生成 AI 待确认提示"):
            if raw_note.strip():
                note_id = insert_interview_note(
                    project_id,
                    interview_type,
                    raw_note,
                    interviewee_name,
                    interviewee_role,
                    organization,
                    interview_date,
                    st.session_state.get("display_name", "本地研究员"),
                )
                analyze_interview_note(project_id, note_id)
                st.success("纪要已保存，并生成待确认 AI 提示。")
                st.rerun()
            else:
                st.warning("请填写纪要原文。")
    if bundle.get("interview_notes"):
        st.dataframe(
            [
                {
                    "类型": INTERVIEW_TYPE_LABELS.get(item["interview_type"], item["interview_type"]),
                    "对象": item["interviewee_name"],
                    "角色": item["interviewee_role"],
                    "机构": item["organization"],
                    "日期": item["interview_date"],
                    "摘要": item["summary"],
                    "时间": item["created_at"],
                }
                for item in bundle["interview_notes"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无访谈纪要。")


def render_memo_and_human_decision(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("Memo 与决策记录")
    render_pending_ai_suggestions(project_id)
    st.divider()
    project = bundle["project"]
    with st.form(f"human_status_{project_id}"):
        status_keys = list(HUMAN_PROJECT_STATUS_LABELS)
        current_status = project.get("human_project_status") or "inbox"
        new_status = st.selectbox(
            "项目阶段",
            status_keys,
            index=status_keys.index(current_status) if current_status in status_keys else 0,
            format_func=lambda value: HUMAN_PROJECT_STATUS_LABELS[value],
            key=f"human_status_select_{project_id}",
        )
        reason_category = st.selectbox(
            "人工原因分类",
            ["材料不足，暂缓", "需要进一步访谈", "需要补充财务材料", "需要外部核验", "进入轻尽调", "进入完整尽调", "准备 memo", "提交投委会", "人工决定归档", "长期跟踪", "其他"],
            key=f"human_reason_category_{project_id}",
        )
        reason = st.text_area("人工说明", key=f"human_reason_{project_id}")
        if st.form_submit_button("保存人工状态"):
            update_human_project_status(project_id, new_status, reason, reason_category, st.session_state.get("display_name", "本地研究员"))
            st.session_state.project_id = project_id
            st.session_state.page = "项目池"
            st.session_state.last_human_status_update = {
                "project_id": project_id,
                "company_name": project["company_name"],
                "new_status": new_status,
            }
            st.rerun()
    st.markdown("#### 人工决策记录")
    if bundle.get("human_decision_logs"):
        st.dataframe(
            [
                {
                    "从": HUMAN_PROJECT_STATUS_LABELS.get(item["previous_status"], item["previous_status"]),
                    "到": HUMAN_PROJECT_STATUS_LABELS.get(item["new_status"], item["new_status"]),
                    "原因": item["decision_reason_category"],
                    "说明": item["decision_reason"],
                    "操作人": item["decided_by"],
                    "时间": item["created_at"],
                }
                for item in bundle["human_decision_logs"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无人工决策记录。")
    st.divider()
    st.markdown("#### Memo 分节草稿")
    if st.button("生成 / 刷新 Memo 分节草稿", key=f"refresh_memo_sections_{project_id}"):
        generate_memo_from_data(project_id)
        st.success("Memo 分节草稿已刷新。")
        st.rerun()
    if bundle.get("memo_sections"):
        for section in bundle["memo_sections"]:
            with st.expander(section["section_title"], expanded=False):
                st.markdown(section["ai_draft"] or "暂无草稿内容。")
    else:
        st.info("暂无 memo 分节草稿。")
    st.markdown("#### 项目事件")
    if bundle.get("project_events"):
        st.dataframe(
            [
                {
                    "事件": item["event_type"],
                    "摘要": item["event_summary"],
                    "来源": item["actor_type"],
                    "操作人": item["actor_name"],
                    "时间": item["created_at"],
                }
                for item in bundle["project_events"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无项目事件。")
    st.divider()
    memo_tab(project_id, bundle)


def main() -> None:
    style()
    init_db()
    st.sidebar.title("AI 投研工作台")
    st.sidebar.caption("项目筛选 · 材料核验 · 尽调备忘")
    page_aliases = {
        "项目漏斗": "项目池",
        "项目工作台": "项目详情",
        "基金策略配置": "投资策略",
    }
    st.session_state.page = page_aliases.get(st.session_state.get("page", "项目池"), st.session_state.get("page", "项目池"))
    pages = ["项目池", "项目详情", "投资策略"]
    if st.session_state.page not in pages:
        st.session_state.page = "项目池"
    page = st.sidebar.radio("页面", pages, index=pages.index(st.session_state.page))
    st.session_state.page = page
    st.session_state.display_name = st.sidebar.text_input("本地研究员", value=st.session_state.get("display_name", "本地研究员"))

    projects = list_projects()
    with st.sidebar.expander("创建项目", expanded=not projects):
        with st.form("create_project_global"):
            company_name = st.text_input("公司名称", placeholder="例如：启明智能")
            st.caption("行业、融资阶段和一句话介绍会在上传 BP 后自动识别。")
            if st.form_submit_button("创建项目", use_container_width=True):
                if not company_name.strip():
                    st.warning("请填写公司名称")
                else:
                    st.session_state.project_id = create_project(company_name)
                    st.session_state.page = "项目详情"
                    st.rerun()

    if page == "项目池":
        render_deal_pipeline()
        return
    if page == "投资策略":
        render_fund_strategy_settings()
        return

    project_id = current_project_id(projects)
    if not project_id:
        st.title("项目详情")
        st.info("暂无项目。请先在左侧创建项目，或回到项目池。")
        return
    if projects:
        project_options = [
            (
                f"{project['company_name']}｜{HUMAN_PROJECT_STATUS_LABELS.get(project.get('human_project_status'), project.get('human_project_status'))}｜{project['id'][-4:]}",
                project["id"],
            )
            for project in projects
        ]
        labels = [label for label, _ in project_options]
        id_by_label = dict(project_options)
        current_label = next((label for label, pid in project_options if pid == project_id), labels[0])
        selected = st.sidebar.radio("项目列表", labels, index=labels.index(current_label))
        project_id = id_by_label[selected]
        st.session_state.project_id = project_id
        with st.sidebar.expander("删除当前项目"):
            st.warning("删除会移除该项目、材料、分析和人工记录。")
            confirm = st.text_input("输入 DELETE 确认删除", key=f"delete_confirm_{project_id}")
            if st.button("确认删除", use_container_width=True, type="secondary", key=f"delete_{project_id}"):
                if confirm == "DELETE":
                    delete_project(project_id)
                    st.session_state.pop("project_id", None)
                    st.session_state.page = "项目池"
                    st.rerun()
                else:
                    st.warning("请输入 DELETE 后再删除。")
    bundle = get_project_bundle(project_id)
    render_project_header(project_id)
    render_global_term_assistant(project_id)
    overview, materials, breakdown, verification, execution, memo = st.tabs(
        ["项目总览", "材料中心", "项目拆解", "问题核验", "尽调执行", "Memo 与记录"]
    )
    with overview:
        render_project_overview(project_id, bundle)
    with materials:
        render_material_center(project_id, bundle)
    with breakdown:
        render_project_breakdown(project_id, bundle)
    with verification:
        render_question_verification(project_id, bundle)
    with execution:
        render_dd_execution(project_id, bundle)
    with memo:
        render_memo_and_records(project_id, bundle)


if __name__ == "__main__":
    main()
