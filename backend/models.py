from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


# --- Carbon / Forecast ---

class CarbonReading(BaseModel):
    timestamp: datetime
    carbon_intensity: float = Field(..., description="gCO2eq/kWh")
    renewable_ratio: float = Field(..., ge=0.0, le=1.0)
    source: str = Field(default="epias", description="'epias' veya 'mock'")


class ForecastPoint(BaseModel):
    timestamp: datetime
    carbon_intensity: float
    renewable_ratio: float
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ptf_tl_per_mwh: Optional[float] = None
    combined_score: Optional[float] = None


class ForecastResponse(BaseModel):
    generated_at: datetime
    source: str
    points: list[ForecastPoint]


# --- Job Queue ---

class PlannedOutage(BaseModel):
    plant_name: str
    start_time: datetime
    end_time: datetime
    capacity_mw: float


class GridStatus(BaseModel):
    dam_fullness_pct: Optional[float]
    dam_trend: Optional[str]
    ptf_tl_per_mwh: Optional[float]
    supply_demand_mw: Optional[float]
    planned_outages: list[PlannedOutage]
    grid_stress: str
    updated_at: datetime
    source: str


class JobStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|scheduled|running|completed|cancelled)$")


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    duration_hours: float = Field(..., gt=0, le=72)
    deadline: Optional[datetime] = None
    priority: int = Field(default=1, ge=1, le=5)
    power_kw: float = Field(..., gt=0, description="İş yükünün güç tüketimi (kW)")
    cost_weight: float = Field(default=0.0, ge=0.0, le=1.0)


class OptimalWindow(BaseModel):
    start_time: datetime
    end_time: datetime
    avg_carbon_intensity: float
    estimated_savings_pct: float
    reasoning: str


class ScheduledJobEntry(BaseModel):
    job_id: int
    name: str
    start_time: datetime
    end_time: datetime
    duration_hours: float
    power_kw: float
    avg_carbon_intensity: float
    estimated_savings_pct: float
    status: str
    color: str
    reasoning: str
    ai_recommendation: Optional[str]


class ScheduleSummary(BaseModel):
    total_jobs: int
    scheduled_jobs: int
    total_carbon_saved_kg: float
    total_energy_kwh: float
    avg_savings_pct: float


class ScheduleResponse(BaseModel):
    generated_at: datetime
    jobs: list[ScheduledJobEntry]
    summary: ScheduleSummary


class ScheduleApproveRequest(BaseModel):
    job_ids: list[int] = Field(default_factory=list)
    demo_mode: bool = False


class JobRecommendation(BaseModel):
    window: str
    date: str
    savings_kg: float
    savings_pct: float
    reasoning: str
    action: str


class JobResponse(BaseModel):
    id: int
    name: str
    duration_hours: float
    deadline: Optional[datetime]
    priority: int
    power_kw: float
    status: str
    created_at: datetime
    scheduled_start: Optional[datetime]
    optimal_window: Optional[OptimalWindow]
    ai_recommendation: Optional[str]
    ai_recommendation_parsed: Optional[JobRecommendation] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


# --- Chat ---

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- Job Templates & Analysis ---

class JobTemplate(BaseModel):
    name: str
    duration_hours: float
    power_kw: float
    priority: int
    description: str


class JobAnalyzeRequest(BaseModel):
    name: str
    duration_hours: float = Field(..., gt=0, le=72)
    power_kw: float = Field(..., gt=0)
    priority: int = Field(default=1, ge=1, le=5)
    deadline: Optional[datetime] = None


class JobAnalyzeResponse(BaseModel):
    reply: str
    optimal_window: Optional[OptimalWindow] = None
    recommendation: Optional[JobRecommendation] = None
    current_carbon_intensity: float


# --- Savings Summary ---

class SavingsSummary(BaseModel):
    total_jobs: int
    optimized_jobs: int
    total_carbon_saved_kg: float
    total_energy_kwh: float
    avg_carbon_intensity: float
    best_saving_pct: float
    period_start: Optional[datetime]
    period_end: Optional[datetime]


# --- Current Carbon (API response wrapper) ---

class CurrentCarbonResponse(BaseModel):
    carbon_intensity: float
    renewable_ratio: float
    timestamp: datetime
    source: str
    updated_minutes_ago: int


# --- Auth ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
