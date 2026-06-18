import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from services.llm import LLMClient
from services.models import LLMConfigError, LLMResponseError
from services.parser import make_chunks
from services.pipeline import analyze_bp, analyze_bp_batch, generate_memo_from_data, validate_bp_analysis
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
            "stage_recommendation": "等待补充信息",
            "risk_level": "high",
            "initial_memo": "# 启明智能 Memo\n\n该建议仅基于当前证据充分度。",
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

    def test_generate_memo_from_structured_data(self):
        project_id = create_project("启明智能", "AI 应用", "天使轮", "")
        analyze_bp(project_id, "bp.txt", b"", "公司已服务 37 家连锁药房客户。", FakeLLM())
        memo = generate_memo_from_data(project_id)
        self.assertIn("最重要看点", memo)
        self.assertIn("关键假设与验证任务", memo)

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


if __name__ == "__main__":
    unittest.main()
