from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import settings
from backend.app.services.parser_rules import save_json
from scripts.parse_pdf_to_json import parse_pdf

SUPPORTED_PDF_SUFFIXES = {".pdf"}
SKIPPED_SUFFIXES = {".doc", ".docx"}


def scan_source_files(source_dir: Path) -> list[Path]:
    return sorted(path for path in source_dir.rglob("*") if path.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description="批量解析题库文件")
    parser.add_argument("--source-dir", type=Path, default=settings.pdf_dir, help="源文件目录")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 个 PDF，0 表示全部")
    parser.add_argument("--no-fallback", action="store_true", help="关闭本地模型兜底")
    args = parser.parse_args()

    settings.ensure_dirs()
    files = scan_source_files(args.source_dir)
    success: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    processed_pdf_count = 0

    for path in files:
        suffix = path.suffix.lower()
        if suffix in SKIPPED_SUFFIXES:
            skipped.append({"file": str(path), "reason": "unsupported_word_document"})
            continue
        if suffix not in SUPPORTED_PDF_SUFFIXES:
            skipped.append({"file": str(path), "reason": "unsupported_file_type"})
            continue
        if args.limit and processed_pdf_count >= args.limit:
            break

        try:
            payload = parse_pdf(path, use_fallback=not args.no_fallback)
            success.append(
                {
                    "file": str(path),
                    "question_count": len(payload["questions"]),
                    "fallback_questions": payload["parse_stats"]["fallback_questions"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"file": str(path), "error": str(exc)})
        processed_pdf_count += 1

    summary = {
        "source_dir": str(args.source_dir),
        "success_count": len(success),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "success": success,
        "failed": failed,
        "skipped": skipped,
    }
    summary_path = settings.data_dir / "batch_extract_summary.json"
    save_json(summary_path, summary)

    print(f"成功: {len(success)}")
    print(f"失败: {len(failed)}")
    print(f"跳过: {len(skipped)}")
    print(f"摘要文件: {summary_path}")


if __name__ == "__main__":
    main()
