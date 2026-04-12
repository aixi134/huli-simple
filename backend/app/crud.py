from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.config import settings
from backend.app.models import AnswerAttempt, Option, Question, QuestionUserState, UploadedFile


def get_question_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Question)) or 0


def get_question_attempt_count(db: Session, question_id: str) -> int:
    return db.scalar(select(func.count()).select_from(AnswerAttempt).where(AnswerAttempt.question_id == question_id)) or 0


def build_scope_question_stmt(
    db: Session,
    source_file: str | None = None,
    *,
    scope_type: str = "all",
):
    del db
    stmt = select(Question).options(selectinload(Question.options), selectinload(Question.user_state))
    if scope_type == "source_file":
        if not source_file:
            return None
        stmt = stmt.where(Question.source_file == source_file)
    elif scope_type == "wrong_only":
        wrong_question_ids = select(AnswerAttempt.question_id).where(AnswerAttempt.is_correct.is_(False)).distinct()
        correct_question_ids = select(AnswerAttempt.question_id).where(AnswerAttempt.is_correct.is_(True)).distinct()
        stmt = stmt.where(Question.id.in_(wrong_question_ids)).where(Question.id.not_in(correct_question_ids)).where(
            (Question.user_state == None) | (Question.user_state.has(hidden_from_wrong_history=False))
        )
    elif source_file:
        stmt = stmt.where(Question.source_file == source_file)
    return stmt


def get_scope_question_count(
    db: Session,
    source_file: str | None = None,
    *,
    scope_type: str = "all",
) -> int:
    if scope_type == "wrong_only":
        wrong_question_ids = select(AnswerAttempt.question_id).where(AnswerAttempt.is_correct.is_(False)).distinct()
        stmt = select(func.count()).select_from(Question).where(Question.id.in_(wrong_question_ids)).where(
            (Question.user_state == None) | (Question.user_state.has(hidden_from_wrong_history=False))
        )
        return db.scalar(stmt) or 0

    stmt = build_scope_question_stmt(db, source_file=source_file, scope_type=scope_type)
    if stmt is None:
        return 0
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def get_scope_progress_stats(
    db: Session,
    source_file: str | None = None,
    *,
    scope_type: str = "all",
) -> dict[str, int]:
    total_count = get_scope_question_count(db, source_file=source_file, scope_type=scope_type)
    remaining_count = 0
    stmt = build_scope_question_stmt(db, source_file=source_file, scope_type=scope_type)
    if stmt is not None:
        attempted_question_ids = select(AnswerAttempt.question_id).distinct()
        correct_question_ids = select(AnswerAttempt.question_id).where(AnswerAttempt.is_correct.is_(True)).distinct()

        remaining_count += db.scalar(
            select(func.count()).select_from(
                stmt.where(Question.id.not_in(attempted_question_ids)).subquery()
            )
        ) or 0
        remaining_count += db.scalar(
            select(func.count()).select_from(
                stmt.where(Question.id.in_(attempted_question_ids)).where(Question.id.not_in(correct_question_ids)).subquery()
            )
        ) or 0

    completed_count = max(total_count - remaining_count, 0)
    return {
        "total_count": total_count,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
    }


def get_random_question(
    db: Session,
    source_file: str | None = None,
    *,
    scope_type: str = "all",
) -> Question | None:
    stmt = build_scope_question_stmt(db, source_file=source_file, scope_type=scope_type)
    if stmt is None:
        return None
    attempted_question_ids = select(AnswerAttempt.question_id).distinct()
    correct_question_ids = select(AnswerAttempt.question_id).where(AnswerAttempt.is_correct.is_(True)).distinct()

    unseen_question = db.scalar(stmt.where(Question.id.not_in(attempted_question_ids)).order_by(func.random()).limit(1))
    if unseen_question is not None:
        return unseen_question

    unresolved_question = db.scalar(
        stmt.where(Question.id.in_(attempted_question_ids)).where(Question.id.not_in(correct_question_ids)).order_by(func.random()).limit(1)
    )
    if unresolved_question is not None:
        return unresolved_question

    return None


def get_question_by_id(db: Session, question_id: str) -> Question | None:
    stmt = (
        select(Question)
        .options(selectinload(Question.options), selectinload(Question.user_state))
        .where(Question.id == question_id)
    )
    return db.scalar(stmt)


def serialize_question(question: Question, *, attempt_count: int = 0) -> dict[str, object]:
    return {
        "id": question.id,
        "question_number": question.question_number,
        "question_type": question.question_type,
        "stem": question.stem,
        "options": [{"label": option.label, "content": option.content} for option in question.options],
        "subject": question.subject,
        "year": question.year,
        "source_file": question.source_file,
        "is_favorite": bool(question.user_state.is_favorite) if question.user_state else False,
        "attempt_count": attempt_count,
    }


def import_question_payload(db: Session, payload: dict[str, object]) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    source_file = str(payload.get("source_file", ""))
    subject = payload.get("subject")
    year = payload.get("year")
    question_type = payload.get("question_type") or "single_choice"
    existing_numbers = set(
        db.scalars(select(Question.question_number).where(Question.source_file == source_file)).all()
    )

    for item in payload.get("questions", []):
        question_number = int(item["number"])
        if question_number in existing_numbers:
            skipped += 1
            continue

        question = Question(
            source_file=source_file,
            subject=subject if isinstance(subject, str) else None,
            year=year if isinstance(year, int) else None,
            question_number=question_number,
            question_type=str(question_type),
            stem=str(item.get("stem", "")).strip(),
            answer=str(item.get("answer", "")).strip().upper(),
            explanation=str(item.get("explanation", "")).strip(),
            parse_method=str(item.get("parse_method", "rule")),
            source_page_start=item.get("source_page_start"),
            source_page_end=item.get("source_page_end"),
        )

        for label, content in dict(item.get("options", {})).items():
            question.options.append(Option(label=str(label), content=str(content).strip()))

        db.add(question)
        existing_numbers.add(question_number)
        inserted += 1

    db.commit()
    return inserted, skipped


def get_uploaded_file(db: Session, source_file: str) -> UploadedFile | None:
    return db.scalar(select(UploadedFile).where(UploadedFile.source_file == source_file))


def get_uploaded_file_by_id(db: Session, file_id: str) -> UploadedFile | None:
    return db.get(UploadedFile, file_id)


def upsert_uploaded_file(
    db: Session,
    *,
    source_file: str,
    file_name: str,
    stored_path: str | None,
    sha256: str | None,
    parsed_question_count: int,
    inserted_count: int,
    skipped_count: int,
    fallback_question_count: int,
) -> UploadedFile:
    record = get_uploaded_file(db, source_file)
    now = datetime.utcnow()
    if record is None:
        record = UploadedFile(
            source_file=source_file,
            file_name=file_name,
            stored_path=stored_path,
            sha256=sha256,
            parsed_question_count=parsed_question_count,
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            fallback_question_count=fallback_question_count,
            created_at=now,
            last_imported_at=now,
        )
        db.add(record)
    else:
        record.file_name = file_name
        record.stored_path = stored_path
        record.sha256 = sha256
        record.parsed_question_count = parsed_question_count
        record.inserted_count = inserted_count
        record.skipped_count = skipped_count
        record.fallback_question_count = fallback_question_count
        record.last_imported_at = now
    db.flush()
    return record


def backfill_uploaded_files(db: Session) -> None:
    uploaded_dir = settings.pdf_dir / "uploaded"
    uploaded_paths = list(uploaded_dir.glob("*.pdf")) if uploaded_dir.exists() else []
    existing_sources = set(db.scalars(select(UploadedFile.source_file)).all())
    source_files = db.scalars(
        select(Question.source_file).where(Question.source_file.like("pdf-upload:%")).distinct()
    ).all()

    for source_file in source_files:
        if source_file in existing_sources:
            continue
        hash_value = source_file.removeprefix("pdf-upload:")
        matched_path = next((path for path in uploaded_paths if sha256(path.read_bytes()).hexdigest() == hash_value), None)
        file_name = matched_path.name.split("-", 1)[1] if matched_path and "-" in matched_path.name else source_file
        question_count = db.scalar(select(func.count()).select_from(Question).where(Question.source_file == source_file)) or 0
        record = UploadedFile(
            source_file=source_file,
            sha256=hash_value or None,
            file_name=file_name,
            stored_path=str(matched_path) if matched_path else None,
            parsed_question_count=question_count,
            inserted_count=question_count,
            skipped_count=0,
            fallback_question_count=0,
        )
        db.add(record)

    db.commit()


def list_uploaded_files(db: Session) -> list[dict[str, object]]:
    backfill_uploaded_files(db)
    question_counts = dict(
        db.execute(
            select(Question.source_file, func.count(Question.id))
            .where(Question.source_file.like("pdf-upload:%"))
            .group_by(Question.source_file)
        ).all()
    )
    records = db.scalars(select(UploadedFile).order_by(UploadedFile.last_imported_at.desc())).all()
    result: list[dict[str, object]] = []
    for record in records:
        result.append(
            {
                "id": record.id,
                "source_file": record.source_file,
                "file_name": record.file_name,
                "parsed_question_count": record.parsed_question_count,
                "inserted_count": record.inserted_count,
                "skipped_count": record.skipped_count,
                "fallback_question_count": record.fallback_question_count,
                "question_count": int(question_counts.get(record.source_file, 0)),
                "created_at": record.created_at,
                "last_imported_at": record.last_imported_at,
            }
        )
    return result


def get_or_create_question_user_state(db: Session, question_id: str) -> QuestionUserState:
    state = db.scalar(select(QuestionUserState).where(QuestionUserState.question_id == question_id))
    if state is None:
        state = QuestionUserState(question_id=question_id)
        db.add(state)
        db.flush()
    return state


def update_question_user_state(
    db: Session,
    *,
    question_id: str,
    is_favorite: bool | None = None,
    hidden_from_wrong_history: bool | None = None,
) -> QuestionUserState:
    question = db.get(Question, question_id)
    if question is None:
        raise ValueError("题目不存在")
    state = get_or_create_question_user_state(db, question_id)
    if is_favorite is not None:
        state.is_favorite = is_favorite
    if hidden_from_wrong_history is not None:
        state.hidden_from_wrong_history = hidden_from_wrong_history
    state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    return state


def delete_question(db: Session, question_id: str) -> bool:
    question = db.get(Question, question_id)
    if question is None:
        return False
    db.delete(question)
    db.commit()
    return True


def delete_uploaded_file(db: Session, file_id: str) -> dict[str, object] | None:
    record = get_uploaded_file_by_id(db, file_id)
    if record is None:
        return None

    source_file = record.source_file
    file_name = record.file_name
    stored_path = record.stored_path
    questions = db.scalars(select(Question).where(Question.source_file == source_file)).all()
    deleted_question_count = len(questions)
    for question in questions:
        db.delete(question)
    db.delete(record)
    db.commit()

    pdf_deleted = False
    if stored_path:
        path = Path(stored_path)
        if path.exists():
            path.unlink()
            pdf_deleted = True

    return {
        "file_id": file_id,
        "source_file": source_file,
        "file_name": file_name,
        "deleted_question_count": deleted_question_count,
        "pdf_deleted": pdf_deleted,
        "deleted": True,
    }


def create_answer_attempt(
    db: Session,
    *,
    question: Question,
    selected_answer: str,
    correct_answer: str,
    is_correct: bool,
) -> AnswerAttempt:
    attempt = AnswerAttempt(
        question_id=question.id,
        source_file=question.source_file,
        selected_answer=selected_answer,
        correct_answer=correct_answer,
        is_correct=is_correct,
    )
    db.add(attempt)
    if not is_correct:
        state = get_or_create_question_user_state(db, question.id)
        state.hidden_from_wrong_history = False
        state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(attempt)
    return attempt


def display_file_name(source_file: str, file_name_map: dict[str, str] | None = None) -> str:
    if file_name_map and source_file in file_name_map:
        return file_name_map[source_file]
    source_path = source_file.strip()
    if "/" in source_path or source_path.endswith(".pdf"):
        return source_path.rsplit("/", 1)[-1]
    return source_file


def list_wrong_answer_history(
    db: Session,
    source_file: str | None = None,
    *,
    favorites_only: bool = False,
) -> list[dict[str, object]]:
    backfill_uploaded_files(db)
    stmt = (
        select(AnswerAttempt)
        .options(
            selectinload(AnswerAttempt.question).selectinload(Question.options),
            selectinload(AnswerAttempt.question).selectinload(Question.user_state),
        )
        .where(AnswerAttempt.is_correct.is_(False))
        .order_by(AnswerAttempt.answered_at.desc())
    )
    if source_file:
        stmt = stmt.where(AnswerAttempt.source_file == source_file)
    attempts = db.scalars(stmt).all()
    file_name_map = {
        item[0]: item[1]
        for item in db.execute(select(UploadedFile.source_file, UploadedFile.file_name)).all()
    }
    seen_question_ids: set[str] = set()
    result: list[dict[str, object]] = []
    for attempt in attempts:
        question = attempt.question
        if attempt.question_id in seen_question_ids or question is None:
            continue
        state = question.user_state
        is_favorite = bool(state.is_favorite) if state else False
        is_hidden = bool(state.hidden_from_wrong_history) if state else False
        if favorites_only and not is_favorite:
            continue
        if not favorites_only and is_hidden:
            continue
        seen_question_ids.add(attempt.question_id)
        result.append(
            {
                "attempt_id": attempt.id,
                "question_id": attempt.question_id,
                "source_file": attempt.source_file,
                "file_name": display_file_name(attempt.source_file, file_name_map),
                "question_number": question.question_number,
                "stem": question.stem,
                "subject": question.subject,
                "year": question.year,
                "selected_answer": attempt.selected_answer,
                "correct_answer": attempt.correct_answer,
                "answered_at": attempt.answered_at,
                "options": [{"label": option.label, "content": option.content} for option in question.options],
                "explanation": question.explanation,
                "attempt_count": get_question_attempt_count(db, question.id),
                "is_favorite": is_favorite,
                "hidden_from_wrong_history": is_hidden,
            }
        )
    return result


def list_practice_record_buckets(db: Session, source_file: str | None = None) -> list[dict[str, object]]:
    backfill_uploaded_files(db)
    stmt = (
        select(AnswerAttempt)
        .options(selectinload(AnswerAttempt.question))
        .order_by(AnswerAttempt.answered_at.desc())
    )
    if source_file:
        stmt = stmt.where(AnswerAttempt.source_file == source_file)
    attempts = db.scalars(stmt).all()
    file_name_map = {
        item[0]: item[1]
        for item in db.execute(select(UploadedFile.source_file, UploadedFile.file_name)).all()
    }

    buckets: dict[datetime, dict[str, object]] = {}
    ordered_keys: list[datetime] = []
    for attempt in attempts:
        question = attempt.question
        if question is None:
            continue
        bucket_start = attempt.answered_at.replace(second=0, microsecond=0)
        if bucket_start not in buckets:
            buckets[bucket_start] = {
                "bucket_start": bucket_start,
                "bucket_end": bucket_start + timedelta(minutes=1),
                "attempt_count": 0,
                "correct_count": 0,
                "wrong_count": 0,
                "items": [],
            }
            ordered_keys.append(bucket_start)
        bucket = buckets[bucket_start]
        bucket["attempt_count"] += 1
        if attempt.is_correct:
            bucket["correct_count"] += 1
        else:
            bucket["wrong_count"] += 1
        bucket["items"].append(
            {
                "attempt_id": attempt.id,
                "question_id": attempt.question_id,
                "source_file": attempt.source_file,
                "file_name": display_file_name(attempt.source_file, file_name_map),
                "question_number": question.question_number,
                "stem": question.stem,
                "selected_answer": attempt.selected_answer,
                "correct_answer": attempt.correct_answer,
                "is_correct": attempt.is_correct,
                "answered_at": attempt.answered_at,
            }
        )

    return [buckets[key] for key in ordered_keys]
