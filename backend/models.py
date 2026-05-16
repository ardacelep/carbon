from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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


class ForecastResponse(BaseModel):
    generated_at: datetime
    source: str
    points: list[ForecastPoint]


# --- Job Queue ---

class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    duration_hours: float = Field(..., gt=0, le=72)
    deadline: Optional[datetime] = None
    priority: int = Field(default=1, ge=1, le=5)
    power_kw: float = Field(..., gt=0, description="İş yükünün güç tüketimi (kW)")


class OptimalWindow(BaseModel):
    start_time: datetime
    end_time: datetime
    avg_carbon_intensity: float
    estimated_savings_pct: float
    reasoning: str


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
