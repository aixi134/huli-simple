from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OptionOut(BaseModel):
    label: str
    content: str


class QuestionOut(BaseModel):
    id: str
    question_number: int
    question_type: str
    stem: str
    options: list[OptionOut]
    subject: str | None = None
    year: int | None = None
    source_file: str
    is_favorite: bool = False
    attempt_count: int = 0


class SubmitAnswerIn(BaseModel):
    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=8)


class SubmitAnswerOut(BaseModel):
    correct: bool
    answer: str
    explanation: str
    attempt_count: int = 0


class AIExplanationOut(BaseModel):
    explanation: str


class ImportPdfOut(BaseModel):
    file_name: str
    source_file: str
    parsed_question_count: int
    inserted_count: int
    skipped_count: int
    fallback_question_count: int
    failed_question_count: int = 0
    errors: list[str] = Field(default_factory=list)
    status: str = "success"
    message: str


class BatchImportOut(BaseModel):
    total_files: int
    success_file_count: int
    partial_file_count: int
    failed_file_count: int
    total_inserted_count: int
    total_skipped_count: int
    total_parsed_question_count: int
    results: list[ImportPdfOut]


class UploadedFileOut(BaseModel):
    id: str
    source_file: str
    file_name: str
    parsed_question_count: int
    inserted_count: int
    skipped_count: int
    fallback_question_count: int
    question_count: int
    created_at: datetime
    last_imported_at: datetime


class WrongAnswerHistoryItemOut(BaseModel):
    attempt_id: str
    question_id: str
    source_file: str
    file_name: str
    question_number: int
    stem: str
    subject: str | None = None
    year: int | None = None
    selected_answer: str
    correct_answer: str
    answered_at: datetime
    options: list[OptionOut] = Field(default_factory=list)
    explanation: str = ""
    attempt_count: int = 0
    is_favorite: bool = False
    hidden_from_wrong_history: bool = False


class QuestionUserStateUpdateIn(BaseModel):
    is_favorite: bool | None = None
    hidden_from_wrong_history: bool | None = None


class QuestionUserStateOut(BaseModel):
    question_id: str
    is_favorite: bool = False
    hidden_from_wrong_history: bool = False


class QuestionDeleteOut(BaseModel):
    question_id: str
    deleted: bool = True


class PracticeRecordItemOut(BaseModel):
    attempt_id: str
    question_id: str
    source_file: str
    file_name: str
    question_number: int
    stem: str
    selected_answer: str
    correct_answer: str
    is_correct: bool
    answered_at: datetime


class PracticeRecordBucketOut(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    attempt_count: int
    correct_count: int
    wrong_count: int
    items: list[PracticeRecordItemOut] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str
    question_count: int
