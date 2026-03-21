"""
AI-Mentor Agent Service — Pydantic Schemas
Request/response models for all API endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from enum import Enum


class AgentId(str, Enum):
    ACADEMIC    = "academic"
    PREDICTION  = "prediction"
    EMOTIONAL   = "emotional"
    LEARNING    = "learning"
    SCHEDULE    = "schedule"
    CAREER      = "career"
    RAG         = "rag"
    MULTIMODAL  = "multimodal"
    ORCHESTRATOR = "orchestrator"


class Language(str, Enum):
    EN = "en"
    TA = "ta"


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    agent: Optional[AgentId] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., description="UUID chat session")
    student_id: str = Field(..., description="Anonymised student ID")
    lang: Language = Language.EN
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    upload_url: Optional[str] = None       # PDF / image URL if uploaded


class Citation(BaseModel):
    label: str
    source: str


class AgentResponseChunk(BaseModel):
    agent: AgentId
    content: str
    citations: list[Citation] = []
    is_final: bool = False


class ChatResponse(BaseModel):
    session_id: str
    agent: AgentId
    content: str
    citations: list[Citation] = []
    tokens_used: int = 0
    model_used: str = ""
    ui_card: Optional[Any] = None           # generative UI widget dict or None
    suggested_actions: list[Any] = []       # [{label, prompt, icon}]
    xp_awarded: int = 0                     # XP earned this turn


# ── Student ────────────────────────────────────────────────────────────────────

class SubjectData(BaseModel):
    code: str
    name: str
    grade: float
    attendance: int
    credit_weight: int
    bloom_level: int
    status: Literal["safe", "watch", "risk"]
    predicted: float


class StudentProfile(BaseModel):
    id: str
    name: str
    department: str
    year: int
    semester: int
    college: str
    current_cgpa: float
    cgpa_history: list[float]
    attendance_overall: int
    subjects: list[SubjectData]
    arrears: list[str] = []
    exam_days: int
    predicted_cgpa: float
    predicted_cgpa_range: tuple[float, float]
    study_streak: int


# ── Predictions ────────────────────────────────────────────────────────────────

class SubjectPrediction(BaseModel):
    code: str
    name: str
    current_grade: float
    predicted_grade: float
    attendance: int
    credit_weight: int
    status: Literal["safe", "watch", "risk"]
    arrear_probability: float          # 0.0 – 1.0
    key_drivers: list[str] = []


class PredictionResponse(BaseModel):
    student_id: str
    predicted_cgpa: float
    cgpa_range: tuple[float, float]
    confidence: float                  # 0.0 – 1.0
    subjects: list[SubjectPrediction]
    narrative: str                     # Gemini-generated human-readable summary
    generated_at: str                  # ISO timestamp


# ── Schedule ───────────────────────────────────────────────────────────────────

class StudySlot(BaseModel):
    time: str
    subject: str
    topic: str
    type: Literal["risk", "watch", "safe"]
    duration_min: int


class DayPlan(BaseModel):
    day: str
    date: str
    slots: list[StudySlot]


class ScheduleResponse(BaseModel):
    student_id: str
    week: list[DayPlan]
    total_study_hours: float
    risk_subject_hours: float
    generated_at: str


# ── Health ──────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    agents_ready: list[str]
    db_connected: bool
    llm_ready: bool
