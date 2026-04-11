from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.crud import import_question_payload
from backend.app.db import SessionLocal, init_db


def import_file(json_path: Path) -> tuple[int, int]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        return import_question_payload(db, payload)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="导入结构化题库 JSON 到 SQLite")
    parser.add_argument("json_path", type=Path, nargs="?", help="题库 JSON 文件路径")
    parser.add_argument("--dir", dest="json_dir", type=Path, help="批量导入目录")
    args = parser.parse_args()

    init_db()
    targets: list[Path] = []
    if args.json_path:
        targets.append(args.json_path)
    if args.json_dir:
        targets.extend(sorted(args.json_dir.glob("*.json")))
    if not targets:
        raise SystemExit("请提供 json_path 或 --dir")

    total_inserted = 0
    total_skipped = 0
    for path in targets:
        inserted, skipped = import_file(path)
        total_inserted += inserted
        total_skipped += skipped
        print(f"{path.name}: inserted={inserted}, skipped={skipped}")

    print(f"总新增: {total_inserted}")
    print(f"总跳过: {total_skipped}")


if __name__ == "__main__":
    main()
