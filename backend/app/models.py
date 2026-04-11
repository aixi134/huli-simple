from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_file: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    parsed_question_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_question_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("source_file", "question_number", name="uq_questions_source_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_file: Mapped[str] = mapped_column(String(1024), index=True)
    subject: Mapped[str | None] = mapped_column(String(128), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_number: Mapped[int] = mapped_column(Integer, index=True)
    question_type: Mapped[str] = mapped_column(String(64), default="single_choice")
    stem: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text, default="")
    parse_method: Mapped[str] = mapped_column(String(32), default="rule")
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    options: Mapped[list[Option]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Option.label",
    )
    attempts: Mapped[list[AnswerAttempt]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="AnswerAttempt.answered_at.desc()",
    )
    user_state: Mapped[QuestionUserState | None] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (UniqueConstraint("question_id", "label", name="uq_options_question_label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(8))
    content: Mapped[str] = mapped_column(Text)

    question: Mapped[Question] = relationship(back_populates="options")


class AnswerAttempt(Base):
    __tablename__ = "answer_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    source_file: Mapped[str] = mapped_column(String(1024), index=True)
    selected_answer: Mapped[str] = mapped_column(String(16))
    correct_answer: Mapped[str] = mapped_column(String(16))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    question: Mapped[Question] = relationship(back_populates="attempts")


class QuestionUserState(Base):
    __tablename__ = "question_user_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), unique=True, index=True
    )
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hidden_from_wrong_history: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    question: Mapped[Question] = relationship(back_populates="user_state")
