import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.parser import make_chunks, parse_document


class ParserTest(unittest.TestCase):
    def test_make_chunks_keeps_source_page_and_section(self):
        chunks = make_chunks("公司已服务客户。\n\n团队来自医疗信息化行业。")
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["page_number"], 1)
        self.assertTrue(chunks[0]["id"].startswith("chunk_"))
        self.assertEqual(chunks[1]["section_label"], "团队")

    def test_parse_csv_as_financial_text(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "financial.csv"
            path.write_text("月份,收入,回款\n1月,100,80\n", encoding="utf-8")
            parsed = parse_document(path)
        self.assertEqual(parsed.parser, "csv")
        self.assertIn("收入", parsed.text)
        self.assertTrue(parsed.chunks)

    def test_parse_xlsx_as_financial_text(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("openpyxl not installed")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "financial.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "财务"
            sheet.append(["月份", "收入", "回款"])
            sheet.append(["1月", 100, 80])
            workbook.save(path)
            parsed = parse_document(path)
        self.assertEqual(parsed.parser, "xlsx")
        self.assertIn("收入", parsed.text)
        self.assertTrue(parsed.chunks)


if __name__ == "__main__":
    unittest.main()
