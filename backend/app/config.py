from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_PAGES_DIR = DATA_DIR / "raw_pages"
PARSED_QUESTIONS_DIR = DATA_DIR / "parsed_questions"
FAILED_DIR = DATA_DIR / "failed"
PDF_DIR = REPO_ROOT / "pdf"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    data_dir: Path
    raw_pages_dir: Path
    parsed_questions_dir: Path
    failed_dir: Path
    pdf_dir: Path
    database_path: Path
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    llm_timeout_seconds: int
    ocr_llm_enabled: bool
    ocr_llm_base_url: str | None
    ocr_llm_api_key: str | None
    ocr_llm_model: str | None
    ocr_llm_provider: str
    ocr_llm_timeout_seconds: int
    cors_origins: list[str]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_pages_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_questions_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)


llm_timeout_seconds = int(os.getenv("QUIZ_LLM_TIMEOUT", "120"))

settings = Settings(
    repo_root=REPO_ROOT,
    data_dir=DATA_DIR,
    raw_pages_dir=RAW_PAGES_DIR,
    parsed_questions_dir=PARSED_QUESTIONS_DIR,
    failed_dir=FAILED_DIR,
    pdf_dir=PDF_DIR,
    database_path=DATA_DIR / "quiz.db",
    llm_base_url=os.getenv("QUIZ_LLM_BASE_URL", "http://127.0.0.1:8888/v1").rstrip("/"),
    llm_api_key=os.getenv("QUIZ_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
    llm_model=os.getenv("QUIZ_LLM_MODEL", "Qwen3.5-27B-Claude-4.6-Opus-Distilled-MLX-4bit"),
    llm_timeout_seconds=llm_timeout_seconds,
    ocr_llm_enabled=env_bool("QUIZ_OCR_LLM_ENABLED", False),
    ocr_llm_base_url=(os.getenv("QUIZ_OCR_LLM_BASE_URL", "").strip().rstrip("/") or None),
    ocr_llm_api_key=os.getenv("QUIZ_OCR_LLM_API_KEY") or None,
    ocr_llm_model=os.getenv("QUIZ_OCR_LLM_MODEL") or None,
    ocr_llm_provider=os.getenv("QUIZ_OCR_LLM_PROVIDER", "").strip(),
    ocr_llm_timeout_seconds=int(os.getenv("QUIZ_OCR_LLM_TIMEOUT", str(llm_timeout_seconds))),
    cors_origins=[
        origin.strip()
        for origin in os.getenv(
            "QUIZ_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173",
        ).split(",")
        if origin.strip()
    ],
)
