from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from backend.app import crud
from backend.app.config import settings
from scripts.parse_pdf_to_json import parse_pdf


@dataclass
class ImportResult:
    file_name: str
    source_file: str
    parsed_question_count: int
    inserted_count: int
    skipped_count: int
    fallback_question_count: int
    failed_question_count: int
    errors: list[str]
    status: str
    message: str


@dataclass
class SavedUpload:
    path: Path
    source_file: str
    file_hash: str
    file_name: str


def save_uploaded_pdf(upload: UploadFile) -> SavedUpload:
    suffix = Path(upload.filename or "uploaded.pdf").suffix.lower() or ".pdf"
    file_name = Path(upload.filename or "uploaded.pdf").name
    if suffix != ".pdf":
        raise ValueError("仅支持 PDF 文件")

    target_dir = settings.pdf_dir / "uploaded"
    target_dir.mkdir(parents=True, exist_ok=True)

    upload.file.seek(0)
    file_bytes = upload.file.read()
    file_hash = sha256(file_bytes).hexdigest()
    target_path = target_dir / f"{file_hash}-{file_name}"
    if not target_path.exists():
        target_path.write_bytes(file_bytes)

    return SavedUpload(
        path=target_path,
        source_file=f"pdf-upload:{file_hash}",
        file_hash=file_hash,
        file_name=file_name,
    )


def import_uploaded_pdf(db: Session, upload: UploadFile) -> ImportResult:
    saved_upload = save_uploaded_pdf(upload)
    payload = parse_pdf(saved_upload.path, use_fallback=True)
    payload["source_file"] = saved_upload.source_file
    for item in payload.get("questions", []):
        if isinstance(item, dict):
            item["source_file"] = saved_upload.source_file
    inserted_count, skipped_count = crud.import_question_payload(db, payload)
    parsed_question_count = len(payload.get("questions", []))
    parse_stats = payload.get("parse_stats", {})
    fallback_question_count = int(parse_stats.get("fallback_questions", 0))
    failed_question_count = int(parse_stats.get("failed_questions", 0))
    errors = [str(item) for item in parse_stats.get("question_errors", [])]
    crud.upsert_uploaded_file(
        db,
        source_file=saved_upload.source_file,
        file_name=saved_upload.file_name,
        stored_path=str(saved_upload.path),
        sha256=saved_upload.file_hash,
        parsed_question_count=parsed_question_count,
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        fallback_question_count=fallback_question_count,
    )
    db.commit()
    status = "failed"
    message = "导入失败"
    if parsed_question_count > 0 and failed_question_count > 0:
        status = "partial_success"
        message = f"导入完成，跳过 {failed_question_count} 道异常题"
    elif parsed_question_count > 0:
        status = "success"
        message = "导入完成"
    return ImportResult(
        file_name=upload.filename or saved_upload.path.name,
        source_file=saved_upload.source_file,
        parsed_question_count=parsed_question_count,
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        fallback_question_count=fallback_question_count,
        failed_question_count=failed_question_count,
        errors=errors,
        status=status,
        message=message,
    )


def import_uploaded_pdfs(db: Session, uploads: list[UploadFile]) -> list[ImportResult]:
    results: list[ImportResult] = []
    for upload in uploads:
        try:
            results.append(import_uploaded_pdf(db, upload))
        except Exception as exc:  # noqa: BLE001
            results.append(
                ImportResult(
                    file_name=upload.filename or "未命名文件",
                    source_file="",
                    parsed_question_count=0,
                    inserted_count=0,
                    skipped_count=0,
                    fallback_question_count=0,
                    failed_question_count=0,
                    errors=[str(exc)],
                    status="failed",
                    message=str(exc),
                )
            )
    return results
