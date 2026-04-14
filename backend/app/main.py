from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app import crud, schemas
from backend.app.config import settings
from backend.app.db import get_db, init_db
from backend.app.services.explainer import explain_with_gemma, stream_explanation_with_gemma
from backend.app.services.importer import import_uploaded_pdf, import_uploaded_pdfs
from backend.app.services.weakness_analysis import recommend_weakness_study_plan


LLM_MISSING_KEY_MESSAGE = "未设置 QUIZ_LLM_API_KEY 或 OPENAI_API_KEY，无法生成 AI 解析"

app = FastAPI(title="Quiz System API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_dirs()
    init_db()


@app.get("/health", response_model=schemas.HealthOut)
def health(db: Session = Depends(get_db)) -> schemas.HealthOut:
    return schemas.HealthOut(status="ok", question_count=crud.get_question_count(db))


@app.get("/files", response_model=list[schemas.UploadedFileOut])
def list_files(db: Session = Depends(get_db)) -> list[schemas.UploadedFileOut]:
    return [schemas.UploadedFileOut(**item) for item in crud.list_uploaded_files(db)]


@app.delete("/files/{file_id}", response_model=schemas.UploadedFileDeleteOut)
def delete_file(file_id: str, db: Session = Depends(get_db)) -> schemas.UploadedFileDeleteOut:
    deleted = crud.delete_uploaded_file(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在")
    return schemas.UploadedFileDeleteOut(**deleted)


@app.get("/scope/stats", response_model=schemas.ScopeStatsOut)
def scope_stats(
    source_file: str | None = Query(default=None),
    scope_type: Literal["all", "source_file", "wrong_only"] = Query(default="all"),
    db: Session = Depends(get_db),
) -> schemas.ScopeStatsOut:
    normalized_source = None if not source_file or source_file == "all" else source_file
    return schemas.ScopeStatsOut(**crud.get_scope_progress_stats(db, source_file=normalized_source, scope_type=scope_type))


@app.get("/question/random", response_model=schemas.QuestionOut)
def get_random_question(
    source_file: str | None = Query(default=None),
    scope_type: Literal["all", "source_file", "wrong_only"] = Query(default="all"),
    db: Session = Depends(get_db),
) -> schemas.QuestionOut:
    normalized_source = None if not source_file or source_file == "all" else source_file
    question = crud.get_random_question(db, source_file=normalized_source, scope_type=scope_type)
    if question is None:
        question_count = crud.get_scope_question_count(db, source_file=normalized_source, scope_type=scope_type)
        if scope_type == "wrong_only":
            if question_count > 0:
                raise HTTPException(status_code=404, detail="错题库中的题目已全部答对")
            raise HTTPException(status_code=404, detail="错题库为空，请先做错几题")
        if scope_type == "source_file" and normalized_source:
            if question_count > 0:
                raise HTTPException(status_code=404, detail="该文件中的题目已全部答对")
            raise HTTPException(status_code=404, detail="该文件下暂无题目，请重新选择")
        if normalized_source:
            if question_count > 0:
                raise HTTPException(status_code=404, detail="该文件中的题目已全部答对")
            raise HTTPException(status_code=404, detail="该文件下暂无题目，请重新选择")
        if question_count > 0:
            raise HTTPException(status_code=404, detail="当前范围题目已全部答对")
        raise HTTPException(status_code=404, detail="题库为空，请先导入题目")
    return schemas.QuestionOut(**crud.serialize_question(question, attempt_count=crud.get_question_attempt_count(db, question.id)))


@app.post("/answer", response_model=schemas.SubmitAnswerOut)
def submit_answer(payload: schemas.SubmitAnswerIn, db: Session = Depends(get_db)) -> schemas.SubmitAnswerOut:
    question = crud.get_question_by_id(db, payload.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    submitted = payload.answer.strip().upper()
    correct_answer = question.answer.strip().upper()
    is_correct = submitted == correct_answer
    crud.create_answer_attempt(
        db,
        question=question,
        selected_answer=submitted,
        correct_answer=correct_answer,
        is_correct=is_correct,
    )
    return schemas.SubmitAnswerOut(
        correct=is_correct,
        answer=correct_answer,
        explanation=question.explanation,
        attempt_count=crud.get_question_attempt_count(db, question.id),
    )


@app.post("/import/pdf", response_model=schemas.ImportPdfOut)
def import_pdf(uploaded_file: UploadFile = File(...), db: Session = Depends(get_db)) -> schemas.ImportPdfOut:
    if not uploaded_file.filename:
        raise HTTPException(status_code=400, detail="请选择 PDF 文件")
    if not uploaded_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    try:
        result = import_uploaded_pdf(db, uploaded_file)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.ImportPdfOut(**result.__dict__)


@app.post("/import/pdf/batch", response_model=schemas.BatchImportOut)
def import_pdf_batch(
    uploaded_files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> schemas.BatchImportOut:
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="请选择至少一个 PDF 文件")
    for uploaded_file in uploaded_files:
        if not uploaded_file.filename:
            raise HTTPException(status_code=400, detail="存在未命名文件，请重新选择")
        if not uploaded_file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"仅支持 PDF 文件：{uploaded_file.filename}")

    results = import_uploaded_pdfs(db, uploaded_files)
    return schemas.BatchImportOut(
        total_files=len(results),
        success_file_count=sum(1 for item in results if item.status == "success"),
        partial_file_count=sum(1 for item in results if item.status == "partial_success"),
        failed_file_count=sum(1 for item in results if item.status == "failed"),
        total_inserted_count=sum(item.inserted_count for item in results),
        total_skipped_count=sum(item.skipped_count for item in results),
        total_parsed_question_count=sum(item.parsed_question_count for item in results),
        results=[schemas.ImportPdfOut(**item.__dict__) for item in results],
    )


@app.get("/history/wrong-answers", response_model=list[schemas.WrongAnswerHistoryItemOut])
def wrong_answer_history(
    source_file: str | None = Query(default=None),
    favorites_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[schemas.WrongAnswerHistoryItemOut]:
    normalized_source = None if not source_file or source_file == "all" else source_file
    return [
        schemas.WrongAnswerHistoryItemOut(**item)
        for item in crud.list_wrong_answer_history(db, normalized_source, favorites_only=favorites_only)
    ]


@app.delete("/question/{question_id}", response_model=schemas.QuestionDeleteOut)
def delete_question(question_id: str, db: Session = Depends(get_db)) -> schemas.QuestionDeleteOut:
    deleted = crud.delete_question(db, question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="题目不存在")
    return schemas.QuestionDeleteOut(question_id=question_id, deleted=True)


@app.get("/history/practice-records", response_model=list[schemas.PracticeRecordBucketOut])
def practice_records(
    source_file: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[schemas.PracticeRecordBucketOut]:
    normalized_source = None if not source_file or source_file == "all" else source_file
    return [
        schemas.PracticeRecordBucketOut(**item)
        for item in crud.list_practice_record_buckets(db, normalized_source)
    ]


@app.get("/analysis/weakness", response_model=schemas.WeaknessAnalysisOut)
def weakness_analysis(
    source_file: str | None = Query(default=None),
    scope_type: Literal["all", "source_file", "wrong_only"] = Query(default="all"),
    db: Session = Depends(get_db),
) -> schemas.WeaknessAnalysisOut:
    normalized_source = None if not source_file or source_file == "all" else source_file
    return schemas.WeaknessAnalysisOut(**crud.get_weakness_analysis(db, source_file=normalized_source, scope_type=scope_type))


@app.post("/analysis/weakness/recommendation", response_model=schemas.WeaknessRecommendationOut)
def weakness_recommendation(
    source_file: str | None = Query(default=None),
    scope_type: Literal["all", "source_file", "wrong_only"] = Query(default="all"),
    db: Session = Depends(get_db),
) -> schemas.WeaknessRecommendationOut:
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail=LLM_MISSING_KEY_MESSAGE)
    normalized_source = None if not source_file or source_file == "all" else source_file
    analysis = crud.get_weakness_analysis(db, source_file=normalized_source, scope_type=scope_type)
    if int(analysis.get("wrong_attempt_count", 0)) <= 0:
        raise HTTPException(status_code=400, detail="当前范围下还没有错题，暂时无法生成薄弱点分析")
    try:
        recommendation = recommend_weakness_study_plan(analysis)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.WeaknessRecommendationOut(**recommendation)


@app.patch("/question/{question_id}/wrong-state", response_model=schemas.QuestionUserStateOut)
def update_question_wrong_state(
    question_id: str,
    payload: schemas.QuestionUserStateUpdateIn,
    db: Session = Depends(get_db),
) -> schemas.QuestionUserStateOut:
    if payload.is_favorite is None and payload.hidden_from_wrong_history is None:
        raise HTTPException(status_code=400, detail="请至少传入一个更新字段")
    try:
        state = crud.update_question_user_state(
            db,
            question_id=question_id,
            is_favorite=payload.is_favorite,
            hidden_from_wrong_history=payload.hidden_from_wrong_history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.QuestionUserStateOut(
        question_id=question_id,
        is_favorite=state.is_favorite,
        hidden_from_wrong_history=state.hidden_from_wrong_history,
    )


@app.post("/question/{question_id}/ai-explanation", response_model=schemas.AIExplanationOut)
def ai_explanation(question_id: str, db: Session = Depends(get_db)) -> schemas.AIExplanationOut:
    question = crud.get_question_by_id(db, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail=LLM_MISSING_KEY_MESSAGE)
    try:
        explanation = explain_with_gemma(
            question=question.stem,
            options={option.label: option.content for option in question.options},
            answer=question.answer,
            explanation=question.explanation,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.AIExplanationOut(explanation=explanation)


@app.post("/question/{question_id}/ai-explanation/stream")
def ai_explanation_stream(question_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    question = crud.get_question_by_id(db, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail=LLM_MISSING_KEY_MESSAGE)

    def generate() -> str:
        try:
            yield from stream_explanation_with_gemma(
                question=question.stem,
                options={option.label: option.content for option in question.options},
                answer=question.answer,
                explanation=question.explanation,
            )
        except Exception as exc:  # noqa: BLE001
            yield f"AI 解析生成失败：{exc}"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
