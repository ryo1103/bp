from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.llm import LLMClient
from services.parser import parse_document
from services.pipeline import analyze_bp, generate_memo_from_data
from services.storage import DATA_DIR, UPLOAD_DIR, create_project, get_project_bundle, init_db


def check_tests() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {"ok": result.returncode == 0, "last_line": (result.stderr or result.stdout).strip().splitlines()[-1]}


def check_env() -> dict:
    client = LLMClient()
    return {
        "base_url": client.base_url,
        "model": client.model,
        "api_key_configured": bool(client.api_key),
    }


def find_test_files() -> list[Path]:
    test_dir = ROOT / "test_doc"
    if not test_dir.exists():
        return []
    return [path for path in test_dir.rglob("*") if path.is_file()]


def check_local_parse(files: list[Path]) -> list[dict]:
    rows = []
    for path in files:
        parsed = parse_document(path)
        rows.append(
            {
                "name": path.name,
                "suffix": path.suffix.lower(),
                "parser": parsed.parser,
                "chars": len(parsed.text),
                "chunks": len(parsed.chunks),
                "pages": len({chunk["page_number"] for chunk in parsed.chunks}),
                "warning": parsed.warning,
            }
        )
    return rows


def run_real_llm_analysis(file_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        original_data = DATA_DIR.exists()
        original_uploads = UPLOAD_DIR.exists()
        backup_data = Path(tmp) / "data_backup"
        backup_uploads = Path(tmp) / "uploads_backup"
        if original_data:
            shutil.copytree(DATA_DIR, backup_data)
            shutil.rmtree(DATA_DIR)
        if original_uploads:
            shutil.copytree(UPLOAD_DIR, backup_uploads)
            shutil.rmtree(UPLOAD_DIR)
        try:
            init_db()
            project_id = create_project("test_doc BP 真实分析测试", "待识别", "待确认", "")
            analyze_bp(project_id, file_path.name, file_path.read_bytes(), "", LLMClient())
            memo = generate_memo_from_data(project_id)
            bundle = get_project_bundle(project_id)
            return {
                "ok": True,
                "claims": len(bundle["claims"]),
                "highlights": len(bundle["highlights"]),
                "assumptions": len(bundle["assumptions"]),
                "tasks": len(bundle["tasks"]),
                "memos": len(bundle["memos"]),
                "memo_has_highlights": "最重要看点" in memo,
                "highlights_have_sources": all(item["source_chunk_id"] and item["source_page"] for item in bundle["highlights"]),
            }
        finally:
            if DATA_DIR.exists():
                shutil.rmtree(DATA_DIR)
            if UPLOAD_DIR.exists():
                shutil.rmtree(UPLOAD_DIR)
            if original_data:
                shutil.copytree(backup_data, DATA_DIR)
            if original_uploads:
                shutil.copytree(backup_uploads, UPLOAD_DIR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Readiness check for the BP investment research MVP.")
    parser.add_argument("--send-to-llm", action="store_true", help="Send test_doc content to the configured LLM for real analysis.")
    args = parser.parse_args()

    files = find_test_files()
    print("== Local readiness ==")
    print({"test_files": len(files), "extensions": sorted({path.suffix.lower() for path in files})})
    print({"env": check_env()})
    print({"tests": check_tests()})
    print({"parse": check_local_parse(files)})

    if args.send_to_llm:
        if not files:
            print({"llm_analysis": {"ok": False, "error": "test_doc has no files"}})
            return 1
        print("== Real LLM analysis ==")
        print({"llm_analysis": run_real_llm_analysis(files[0])})
    else:
        print({"llm_analysis": "skipped; pass --send-to-llm only after confidentiality approval"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
