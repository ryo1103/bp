import unittest

from services.parser import make_chunks


class ParserTest(unittest.TestCase):
    def test_make_chunks_keeps_source_page_and_section(self):
        chunks = make_chunks("公司已服务客户。\n\n团队来自医疗信息化行业。")
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["page_number"], 1)
        self.assertTrue(chunks[0]["id"].startswith("chunk_"))
        self.assertEqual(chunks[1]["section_label"], "团队")


if __name__ == "__main__":
    unittest.main()
