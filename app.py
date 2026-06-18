from __future__ import annotations
from typing import Dict, List

import streamlit as st

from services.llm import LLMClient
from services.models import AppError, LLMConfigError, LLMResponseError, RISK_LABELS, STATUS_LABELS
from services.pipeline import analyze_bp_batch, verify_supplementary
from services.storage import (
    create_manual_task,
    create_project,
    delete_project,
    get_project_bundle,
    init_db,
    list_projects,
    update_task,
)


st.set_page_config(page_title="AI 投研验证工作台", layout="wide")


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
    st.markdown(f"**{value or '待确认'}**")


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
            industry = st.text_input("行业", placeholder="AI 应用")
            financing_stage = st.text_input("融资阶段", placeholder="天使轮")
            one_liner = st.text_input("一句话介绍", placeholder="上传 BP 后可由 AI 更新")
            if st.form_submit_button("创建项目", use_container_width=True):
                if not company_name.strip():
                    st.warning("请填写公司名称")
                else:
                    st.session_state.project_id = create_project(company_name, industry, financing_stage, one_liner)
                    st.rerun()

    project_id = current_project_id(projects)
    if projects:
        labels = {
            f"{project['company_name']}｜{project['industry']}｜高风险未验证 {project['unverified_high_risk_count']}": project["id"]
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
                    pill(f"风险：{RISK_LABELS.get(project['risk_level'], project['risk_level'])}"),
                    pill(project["current_recommendation"]),
                ]
            ),
            unsafe_allow_html=True,
        )
    with right:
        st.metric("高风险未验证", project["unverified_high_risk_count"])
        st.metric("已验证任务", project["verified_count"])


def memo_from_bundle(bundle: Dict[str, object]) -> str:
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
        f"- 风险等级：{RISK_LABELS.get(project['risk_level'], project['risk_level'])}",
        "",
        "## 最重要看点",
        "",
    ]
    if bundle["highlights"]:
        lines.extend(
            f"- **{item['title']}**：{item['why_important']}（证据充分度：{item['evidence_level']}，来源 p{item['source_page']}）"
            for item in bundle["highlights"]
        )
    else:
        lines.append("- 暂无。")

    lines.extend(["", "## BP 关键陈述", ""])
    if bundle["claims"]:
        lines.extend(
            f"- {claim['claim_text']}（状态：{STATUS_LABELS.get(claim['verification_status'], claim['verification_status'])}，来源 p{claim['source_page']}）"
            for claim in bundle["claims"]
        )
    else:
        lines.append("- 暂无。")

    lines.extend(["", "## 关键假设", ""])
    if bundle["assumptions"]:
        lines.extend(
            f"- {item['assumption_text']}｜风险：{RISK_LABELS.get(item['risk_level'], item['risk_level'])}｜验证方法：{item['verification_method']}"
            for item in bundle["assumptions"]
        )
    else:
        lines.append("- 暂无。")

    lines.extend(["", "## 验证任务", ""])
    if bundle["tasks"]:
        lines.extend(
            f"- {task['title']}｜风险：{RISK_LABELS.get(task['risk_level'], task['risk_level'])}｜状态：{STATUS_LABELS.get(task['status'], task['status'])}｜缺失证据：{task['missing_evidence']}"
            for task in bundle["tasks"]
        )
    else:
        lines.append("- 暂无。")

    lines.extend(
        [
            "",
            "## 阶段性建议",
            "",
            f"{project['current_recommendation']}。该建议仅基于当前材料的证据充分度，不构成最终投资决策。",
        ]
    )
    return "\n".join(lines)


def upload_bp_tab(project_id: str, bundle: Dict[str, object]) -> None:
    has_bp_analysis = bool(bundle["claims"] or bundle["highlights"] or bundle["assumptions"])
    st.subheader("项目概览")
    project = bundle["project"]
    info_cols = st.columns(4)
    with info_cols[0]:
        field_card("公司", project["company_name"])
    with info_cols[1]:
        field_card("行业", project["industry"])
    with info_cols[2]:
        field_card("融资阶段", project["financing_stage"])
    with info_cols[3]:
        field_card("阶段性建议", project["current_recommendation"])

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("BP 陈述", len(bundle["claims"]))
    with metric_cols[1]:
        st.metric("最重要看点", len(bundle["highlights"]))
    with metric_cols[2]:
        st.metric("关键假设", len(bundle["assumptions"]))
    with metric_cols[3]:
        st.metric("验证任务", len(bundle["tasks"]))

    high_risk_tasks = [
        task for task in bundle["tasks"] if task["risk_level"] == "high" and task["status"] != "verified"
    ]
    st.markdown("#### 高风险未验证项")
    if high_risk_tasks:
        for task in high_risk_tasks[:5]:
            with st.container(border=True):
                st.markdown(f"**{task['title']}**")
                st.caption(
                    f"状态：{STATUS_LABELS.get(task['status'], task['status'])}｜缺失证据：{task['missing_evidence']}"
                )
    else:
        st.info("暂无高风险未验证项。")

    st.divider()
    st.markdown("#### 已上传材料")
    if bundle["documents"]:
        for document in bundle["documents"]:
            with st.container(border=True):
                cols = st.columns([2, 1, 1])
                with cols[0]:
                    st.markdown(f"**{document['file_name']}**")
                with cols[1]:
                    st.caption(f"类型：{document['document_type']}")
                with cols[2]:
                    st.caption(f"状态：{document['parse_status']}")
                st.write(document["summary"] or "暂无摘要")
    else:
        st.info("暂无已上传材料。")

    st.divider()
    st.subheader("BP 上传与 AI 综合分析" if not has_bp_analysis else "追加 BP / 相关材料并重新综合分析")
    if has_bp_analysis:
        st.caption("新版 BP、业务补充说明、会影响项目基本判断的材料放这里；合同、访谈纪要、财务明细等尽调证据放到“补充材料”。")
    else:
        st.caption("可一次上传多个 BP 文件，也可以直接粘贴正文。")
    with st.form("upload_bp"):
        uploaded_files = st.file_uploader(
            "BP 文件",
            type=["txt", "md", "pdf", "docx", "pptx"],
            accept_multiple_files=True,
        )
        pasted = st.text_area("或粘贴 BP 正文 / 追加说明", height=180)
        submitted = st.form_submit_button("上传并调用 AI 分析" if not has_bp_analysis else "追加并重新综合分析", type="primary")
        if submitted:
            uploads = [{"name": file.name, "content": uploaded_bytes(file)} for file in (uploaded_files or [])]
            if not uploads and not pasted.strip() and not has_bp_analysis:
                st.warning("请至少上传一个 BP 文件或粘贴 BP 正文。")
                return
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
    st.subheader("公司结构化信息")
    project = bundle["project"]
    info_cols = st.columns(4)
    with info_cols[0]:
        field_card("公司", project["company_name"])
    with info_cols[1]:
        field_card("行业", project["industry"])
    with info_cols[2]:
        field_card("融资阶段", project["financing_stage"])
    with info_cols[3]:
        field_card("风险等级", RISK_LABELS.get(project["risk_level"], project["risk_level"]))
    st.caption("一句话介绍")
    st.markdown(f"**{project['one_liner'] or '待确认'}**")

    st.subheader("最重要看点")
    if bundle["highlights"]:
        for item in bundle["highlights"]:
            with st.container(border=True):
                st.markdown(f"**{item['title']}**")
                st.write(item["why_important"])
                st.caption(
                    f"对应陈述：{item['linked_claim_text']}｜来源 p{item['source_page']}｜证据充分度：{item['evidence_level']}｜验证方向：{item['verification_direction']}"
                )
    else:
        st.info("上传 BP 并完成 AI 分析后显示最重要看点。")

    st.subheader("BP 陈述清单")
    st.dataframe(
        [
            {
                "陈述": item["claim_text"],
                "类型": item["claim_type"],
                "主题": item["topic"],
                "状态": STATUS_LABELS.get(item["verification_status"], item["verification_status"]),
                "来源页": item["source_page"],
                "来源摘录": item["source_quote"],
            }
            for item in bundle["claims"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("关键假设表")
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


def risk_sort_value(task: Dict[str, object]) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(task["risk_level"]), 3)


def render_task_cards(tasks: List[Dict[str, object]], empty_text: str) -> None:
    if not tasks:
        st.info(empty_text)
        return

    for task in tasks:
        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(f"**{task['title']}**")
                st.caption(f"已有证据：{task['existing_evidence']}")
            with cols[1]:
                st.write(f"风险：{RISK_LABELS.get(task['risk_level'], task['risk_level'])}")
            with cols[2]:
                st.write(f"状态：{STATUS_LABELS.get(task['status'], task['status'])}")

            st.write(f"缺失证据：{task['missing_evidence']}")
            st.write(f"建议材料：{task['suggested_materials']}")
            st.write(f"建议访谈对象：{task['suggested_interviewees']}")
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
    st.subheader("验证任务")
    with st.expander("手动添加验证任务"):
        with st.form("manual_task"):
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
            risk_level = st.selectbox("风险等级", list(RISK_LABELS), format_func=lambda value: RISK_LABELS[value])
            existing_evidence = st.text_area("当前已有证据", placeholder="用户观察到的线索、BP 中对应描述或外部资料")
            missing_evidence = st.text_area("缺失证据", placeholder="还需要哪些材料或数据")
            suggested_materials = st.text_input("建议补充材料", placeholder="客户合同、回款记录、访谈纪要")
            suggested_interviewees = st.text_input("建议访谈对象", placeholder="创始人、客户负责人、财务负责人")
            founder_questions = st.text_area("问创始人的问题", placeholder="希望创始人澄清什么")
            customer_questions = st.text_area("问客户的问题", placeholder="希望客户验证什么")
            user_notes = st.text_input("备注")
            if st.form_submit_button("添加任务", type="primary"):
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
                    st.success("已添加验证任务")
                    st.rerun()

    if not bundle["tasks"]:
        st.info("上传 BP 后，关键假设会自动转化为验证任务。")
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
    pending_tab, verified_tab = st.tabs([f"待验证（{len(pending_tasks)}）", f"已验证（{len(verified_tasks)}）"])
    with pending_tab:
        render_task_cards(pending_tasks, "暂无待验证任务。")
    with verified_tab:
        render_task_cards(verified_tasks, "暂无已验证任务。")


def supplementary_tab(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("补充材料上传与验证")
    with st.form("upload_supp"):
        uploaded = st.file_uploader("补充材料", type=["txt", "md", "pdf", "docx", "pptx"], key="supp_file")
        pasted = st.text_area("或粘贴补充材料正文", height=160)
        submitted = st.form_submit_button("上传并调用 AI 验证", type="primary")
        if submitted:
            try:
                with st.spinner("正在匹配历史验证任务..."):
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
                    "判断": item["judgment"],
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


def memo_tab(project_id: str, bundle: Dict[str, object]) -> None:
    st.subheader("投资 memo")
    if bundle["claims"] or bundle["highlights"] or bundle["assumptions"] or bundle["tasks"]:
        content = memo_from_bundle(bundle)
        st.download_button("下载 Markdown", content, file_name="investment_memo.md", mime="text/markdown")
        st.markdown("#### Memo 预览")
        st.markdown(content)
    elif bundle["memos"]:
        latest = bundle["memos"][-1]
        st.download_button("下载 Markdown", latest["content_markdown"], file_name="investment_memo.md", mime="text/markdown")
        st.markdown("#### Memo 预览")
        st.markdown(latest["content_markdown"])
    else:
        st.info("完成 BP 分析后，这里会自动展示 memo。")


def main() -> None:
    style()
    init_db()
    projects = list_projects()
    project_id = sidebar(projects)
    if not project_id:
        st.title("AI 投研验证工作台")
        st.info("请先在左侧创建项目。")
        return

    bundle = get_project_bundle(project_id)
    show_project_header(bundle)
    overview, analysis, tasks, supplementary, memo = st.tabs(["概览 / BP 上传", "BP 分析", "验证任务", "补充材料", "投资 memo"])
    with overview:
        upload_bp_tab(project_id, bundle)
    with analysis:
        bp_analysis_tab(bundle)
    with tasks:
        tasks_tab(bundle)
    with supplementary:
        supplementary_tab(project_id, bundle)
    with memo:
        memo_tab(project_id, bundle)


if __name__ == "__main__":
    main()
