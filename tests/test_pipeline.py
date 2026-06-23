import os
import re
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from services.llm import LLMClient
from services.models import LLMConfigError, LLMResponseError
from services.parser import make_chunks
from services.pipeline import analyze_bp, analyze_bp_batch, generate_memo_from_data, validate_bp_analysis, verify_supplementary
from services.storage import DATA_DIR, UPLOAD_DIR, create_manual_task, create_project, get_project_bundle, init_db


class FakeLLM:
    def chat_json(self, messages, temperature=0.2):
        chunk_id = "chunk-not-used"
        content = messages[-1]["content"]
        for part in content.split("chunk_id=")[1:]:
            chunk_id = part.split(" ", 1)[0].strip()
            break
        return {
            "company_summary": {
                "company_name": "启明智能",
                "industry": "AI 应用",
                "financing_stage": "天使轮",
                "one_liner": "为连锁药房提供 AI 运营系统",
            },
            "document_summary": "BP 显示公司已有客户和收入，但证据仍来自公司陈述。",
            "bp_claims": [
                {
                    "claim_text": "已服务 37 家连锁药房客户",
                    "claim_type": "data",
                    "topic": "customer_traction",
                    "source_chunk_id": chunk_id,
                    "source_page": 1,
                    "source_quote": "已服务 37 家连锁药房客户",
                }
            ],
            "key_highlights": [
                {
                    "title": f"看点 {i}",
                    "linked_claim_text": "已服务 37 家连锁药房客户",
                    "source_chunk_id": chunk_id,
                    "source_page": 1,
                    "why_important": "客户基础可能说明需求存在。",
                    "evidence_level": "中",
                    "verification_direction": "核验客户合同、回款和续约。",
                }
                for i in range(1, 4)
            ],
            "assumptions": [
                {
                    "assumption_text": f"关键假设 {i}",
                    "importance": "high" if i < 4 else "medium",
                    "risk_level": "high" if i < 4 else "medium",
                    "why_it_matters": "影响商业逻辑成立。",
                    "failure_impact": "如果不成立，增长和收入质量会被高估。",
                    "verification_method": "检查客户合同、回款、访谈和第三方资料。",
                }
                for i in range(1, 6)
            ],
            "verification_tasks": [
                {
                    "title": f"验证任务 {i}",
                    "task_type": "demand",
                    "risk_level": "high" if i < 4 else "medium",
                    "existing_evidence": "BP 公司陈述",
                    "missing_evidence": "缺合同、回款、访谈",
                    "suggested_materials": "客户合同、回款记录",
                    "suggested_interviewees": "创始人、客户负责人",
                    "founder_questions": "有多少付费客户？",
                    "customer_questions": "是否愿意续费？",
                }
                for i in range(1, 6)
            ],
            "sector_analysis": {
                "primary_industry": "医疗健康",
                "sub_sector": "连锁药房 AI 运营系统",
                "target_customer": "连锁药房总部和门店运营团队",
                "value_chain_position": "下游药房运营软件层",
                "replacement_target": "人工运营分析和传统 BI 报表",
                "profit_pool_logic": "若能嵌入药房运营流程，可分享降本增效预算。",
                "summary": "公司处于医疗零售数字化中的垂直 AI 应用环节。",
            },
            "industry_map": [
                {"node_type": "upstream", "label": "药品与数据供应", "description": "提供商品、库存和销售数据。", "is_company_position": False},
                {"node_type": "midstream", "label": "药房运营系统", "description": "连接库存、会员、营销和门店管理。", "is_company_position": True},
                {"node_type": "downstream", "label": "连锁药房", "description": "采购并使用运营系统。", "is_company_position": False},
                {"node_type": "customer", "label": "门店店长", "description": "日常使用建议和报表。", "is_company_position": False},
                {"node_type": "regulator", "label": "药监合规", "description": "影响数据和药品经营合规。", "is_company_position": False},
            ],
            "industry_terms": [
                {"term": "回款周期", "explanation": "客户确认收入后实际付款所需时间。", "relevance": "影响收入质量和现金流。"},
                {"term": "门店动销", "explanation": "商品在门店的实际销售速度。", "relevance": "决定运营优化价值。"},
                {"term": "垂直 SaaS", "explanation": "面向特定行业流程的软件。", "relevance": "决定产品深度和销售方式。"},
                {"term": "续费率", "explanation": "客户到期后继续付费比例。", "relevance": "验证真实需求。"},
                {"term": "客户集中度", "explanation": "收入是否依赖少数客户。", "relevance": "影响收入稳定性。"},
            ],
            "red_flags": [
                {
                    "title": "收入与客户规模需要直接核验",
                    "flag_type": "revenue",
                    "severity": "high",
                    "status": "open",
                    "evidence": "BP 同时声称服务 37 家客户和收入 860 万元，但未给回款依据。",
                    "source_chunk_id": chunk_id,
                    "source_page": 1,
                    "why_it_matters": "若只是合同额或试点口径，收入质量会被高估。",
                    "suggested_verification": "核验合同、发票、银行流水和收入确认口径。",
                }
            ],
            "funding_analysis": {
                "stated_round": "天使轮",
                "inferred_round": "天使轮到 Pre-A 之间",
                "round_confidence": "medium",
                "material_sufficiency": "当前材料对天使轮基本够用，但若按 Pre-A 需要更完整收入、回款和续费证据。",
                "risk_return_profile": "早期轮次上行空间较高，但不确定性仍主要来自收入质量和续费。",
                "stability_assessment": "稳定性弱于成长期项目，客户数量和续费证据仍不足。",
                "payback_cycle_view": "回款周期需要用合同账期、发票和银行流水验证。",
                "investor_signal": "BP 未披露强背书投资人，投资人信号暂弱。",
                "existing_investors": [
                    {
                        "name": "启明天使基金",
                        "investor_type": "institution",
                        "round": "天使轮",
                        "signal_strength": "medium",
                        "why_it_matters": "机构投资人可提供一定背书，但仍需核验实际出资和投后参与。",
                        "needs_verification": "核验工商股东、交割凭证和新闻披露。",
                    }
                ],
                "missing_round_evidence": "缺历史融资协议、估值、投资人出资证明和本轮资金用途拆解。",
                "valuation_fit": "未披露估值，无法判断轮次价格是否匹配。",
                "suggested_checks": "核验历史投资人、估值、资金到账和本轮里程碑。",
            },
            "stage_recommendation": "等待补充信息",
            "risk_level": "high",
            "initial_memo": "# 启明智能 Memo\n\n该建议仅基于当前证据充分度。",
        }


class FakeSupplementLLM:
    def __init__(self, mode="resolve"):
        self.mode = mode

    def chat_json(self, messages, temperature=0.2):
        content = messages[-1]["content"]
        task_id = next(iter(re.findall(r'"id": "(task_[^"]+)"', content)), "")
        flag_id = next(iter(re.findall(r'"id": "(flag_[^"]+)"', content)), "")
        chunk_id = next(iter(re.findall(r"chunk_id=([^ ]+)", content)), "")
        if self.mode == "unrelated":
            return {
                "material_summary": "补充材料介绍了产品路线图。",
                "task_updates": [],
                "red_flag_updates": [],
                "material_resolutions": [
                    {
                        "target_type": "material",
                        "target_id": "",
                        "target_title": "产品路线图",
                        "resolution_status": "new_information",
                        "evidence_text": "材料补充未来产品模块。",
                        "impact_summary": "有助于判断产品规划，但不能解决收入真实性问题。",
                        "remaining_gap": "仍缺合同、回款和客户访谈。",
                    }
                ],
                "financial_analysis": {"summary": "", "revenue_quality": "", "margin_costs": "", "cashflow_quality": "", "customer_concentration": "", "anomalies": "", "bp_conflicts": "", "follow_up_materials": ""},
                "stage_recommendation": "等待补充信息",
                "risk_level": "high",
                "updated_memo": "材料未解决关键疑点。",
            }
        financial = {
            "summary": "财务表显示收入和回款口径。",
            "revenue_quality": "收入需要区分合同额和已回款收入。",
            "margin_costs": "暂未披露完整成本费用。",
            "cashflow_quality": "回款记录可部分支持收入真实性。",
            "customer_concentration": "需要客户维度收入明细。",
            "anomalies": "未发现明显异常波动。",
            "bp_conflicts": "与 BP 860 万收入口径部分一致。",
            "follow_up_materials": "补充银行流水、发票、客户分收入。",
        } if self.mode == "financial" else {"summary": "", "revenue_quality": "", "margin_costs": "", "cashflow_quality": "", "customer_concentration": "", "anomalies": "", "bp_conflicts": "", "follow_up_materials": ""}
        return {
            "material_summary": "补充材料提供合同和回款说明。",
            "task_updates": [
                {
                    "task_id": task_id,
                    "new_status": "partially_verified",
                    "chunk_id": chunk_id,
                    "evidence_text": "材料显示部分客户已付款。",
                    "judgment": "partially_supports",
                    "confidence": 0.7,
                    "still_missing": "仍缺完整银行流水。",
                    "new_questions": "收入确认口径是什么？",
                }
            ],
            "red_flag_updates": [
                {
                    "red_flag_id": flag_id,
                    "new_status": "partially_resolved",
                    "evidence_text": "补充材料提供部分回款记录。",
                    "impact_summary": "收入真实性疑点被部分解释。",
                    "remaining_gap": "仍缺完整客户收入拆分。",
                    "resolution_note": "部分客户回款可支持 BP 口径，但仍未完全闭环。",
                }
            ],
            "material_resolutions": [
                {
                    "target_type": "task",
                    "target_id": task_id,
                    "target_title": "收入真实性",
                    "resolution_status": "partially_resolved",
                    "evidence_text": "部分客户已付款。",
                    "impact_summary": "降低收入完全虚假的风险。",
                    "remaining_gap": "仍缺全量流水。",
                }
            ],
            "financial_analysis": financial,
            "stage_recommendation": "继续看",
            "risk_level": "medium",
            "updated_memo": "补充材料部分解决收入疑点。",
        }


class PipelineTest(unittest.TestCase):
    def setUp(self):
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        init_db()

    def test_missing_llm_key_raises_config_error(self):
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            with patch("services.llm.load_dotenv", lambda: None):
                with self.assertRaises(LLMConfigError):
                    LLMClient().require_configured()
        finally:
            if old_key:
                os.environ["LLM_API_KEY"] = old_key

    def test_validate_requires_three_to_seven_highlights(self):
        chunks = make_chunks("公司已服务 37 家连锁药房客户。")
        payload = FakeLLM().chat_json([{"role": "user", "content": f"chunk_id={chunks[0]['id']} page=1"}])
        payload["key_highlights"] = payload["key_highlights"][:2]
        with self.assertRaises(LLMResponseError):
            validate_bp_analysis(payload, {chunks[0]["id"]})

    def test_analyze_bp_persists_claims_highlights_assumptions_tasks_and_memo(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp(
            project_id,
            "bp.txt",
            b"",
            "公司名称：启明智能\n公司已服务 37 家连锁药房客户，收入达到 860 万元。",
            FakeLLM(),
        )
        bundle = get_project_bundle(project_id)
        self.assertEqual(bundle["project"]["company_name"], "启明智能")
        self.assertEqual(len(bundle["claims"]), 1)
        self.assertEqual(len(bundle["highlights"]), 3)
        self.assertEqual(len(bundle["assumptions"]), 5)
        self.assertEqual(len(bundle["tasks"]), 5)
        self.assertEqual(len(bundle["memos"]), 1)
        self.assertTrue(all(item["source_chunk_id"] for item in bundle["highlights"]))
        self.assertEqual(len(bundle["sector_analyses"]), 1)
        self.assertEqual(len(bundle["industry_map_nodes"]), 5)
        self.assertEqual(len(bundle["industry_terms"]), 5)
        self.assertEqual(len(bundle["red_flags"]), 1)
        self.assertEqual(bundle["red_flags"][0]["status"], "open")
        self.assertEqual(len(bundle["funding_analyses"]), 1)
        self.assertIn("Pre-A", bundle["funding_analyses"][0]["inferred_round"])

    def test_generate_memo_from_structured_data(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp(project_id, "bp.txt", b"", "公司已服务 37 家连锁药房客户。", FakeLLM())
        memo = generate_memo_from_data(project_id)
        self.assertIn("最重要看点", memo)
        self.assertIn("关键假设与验证任务", memo)
        self.assertIn("赛道归类与产业位置", memo)
        self.assertIn("直接异常与红旗", memo)
        self.assertIn("融资轮次与投资人信号", memo)
        self.assertIn("启明天使基金", memo)

    def test_create_manual_task_persists_user_task(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        task_id = create_manual_task(
            project_id,
            "验证核心客户是否真实续费",
            "demand",
            "high",
            "用户手动观察到客户续费口径不清晰",
            "缺续约合同和回款记录",
            "续约合同、回款记录",
            "客户负责人",
            "续约率是多少？",
            "是否愿意继续付费？",
            "优先跟进",
        )
        bundle = get_project_bundle(project_id)
        task = next(item for item in bundle["tasks"] if item["id"] == task_id)
        self.assertEqual(task["title"], "验证核心客户是否真实续费")
        self.assertEqual(task["linked_claim_id"], "")
        self.assertEqual(task["linked_assumption_id"], "")
        self.assertEqual(task["status"], "unverified")

    def test_reanalysis_uses_existing_and_new_bp_materials_without_deleting_manual_tasks(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp_batch(
            project_id,
            [{"name": "bp-part-1.txt", "content": "公司已服务 37 家连锁药房客户。".encode("utf-8")}],
            "",
            include_existing=False,
            llm=FakeLLM(),
        )
        manual_task_id = create_manual_task(
            project_id,
            "手动验证收入回款真实性",
            "financial_quality",
            "high",
            "用户手动添加",
            "缺回款流水",
            "银行流水、发票",
            "财务负责人",
            "收入确认口径是什么？",
            "是否真实付款？",
            "",
        )
        analyze_bp_batch(
            project_id,
            [{"name": "bp-part-2.txt", "content": "补充材料显示公司收入达到 860 万元。".encode("utf-8")}],
            "",
            include_existing=True,
            llm=FakeLLM(),
        )
        bundle = get_project_bundle(project_id)
        self.assertEqual(len([task for task in bundle["tasks"] if task["linked_claim_id"] or task["linked_assumption_id"]]), 5)
        self.assertTrue(any(task["id"] == manual_task_id for task in bundle["tasks"]))
        self.assertEqual(len(bundle["claims"]), 1)
        self.assertEqual(len([document for document in bundle["documents"] if document["document_type"] == "bp"]), 2)

    def test_supplementary_updates_tasks_red_flags_and_resolution_summary(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp(project_id, "bp.txt", b"", "公司已服务 37 家连锁药房客户，收入达到 860 万元。", FakeLLM())
        verify_supplementary(
            project_id,
            "contracts.txt",
            b"",
            "补充材料显示部分客户已付款，并提供合同编号。",
            FakeSupplementLLM(),
        )
        bundle = get_project_bundle(project_id)
        self.assertTrue(any(task["status"] == "partially_verified" for task in bundle["tasks"]))
        self.assertEqual(bundle["red_flags"][0]["status"], "partially_resolved")
        self.assertEqual(len(bundle["supplementary_resolutions"]), 2)

    def test_unrelated_supplementary_summarizes_material_value_without_status_updates(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp(project_id, "bp.txt", b"", "公司已服务 37 家连锁药房客户，收入达到 860 万元。", FakeLLM())
        verify_supplementary(project_id, "roadmap.txt", b"", "补充材料介绍下一代产品路线图。", FakeSupplementLLM("unrelated"))
        bundle = get_project_bundle(project_id)
        self.assertTrue(all(task["status"] == "unverified" for task in bundle["tasks"]))
        self.assertEqual(bundle["red_flags"][0]["status"], "open")
        self.assertEqual(bundle["supplementary_resolutions"][0]["resolution_status"], "new_information")

    def test_financial_csv_material_creates_financial_analysis(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp(project_id, "bp.txt", b"", "公司已服务 37 家连锁药房客户，收入达到 860 万元。", FakeLLM())
        verify_supplementary(
            project_id,
            "financial.csv",
            "月份,收入,回款\n1月,100,80\n".encode("utf-8"),
            "",
            FakeSupplementLLM("financial"),
        )
        bundle = get_project_bundle(project_id)
        self.assertEqual(len(bundle["financial_analyses"]), 1)
        self.assertIn("回款", bundle["financial_analyses"][0]["cashflow_quality"])


if __name__ == "__main__":
    unittest.main()
