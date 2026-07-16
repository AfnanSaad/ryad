# -*- coding: utf-8 -*-
"""
app.py — سيرفر "رياد" (FastAPI)
هذا هو الملف اللي بيستضاف على Render ويعطينا رابط عام دائم.
Figma Plugin بيتواصل مع هذا السيرفر عبر fetch().
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional

from model import ForecastEngine, MAX_FORECAST_MONTHS

app = FastAPI(title="Riyad Financial Twin API", version="1.0.0")

# مهم جدًا: Figma Plugins تشتغل من origin مختلف (null / figma domain)
# فلازم نسمح بكل origins عشان الـ CORS ما يمنع الطلب
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = ForecastEngine()


@app.on_event("startup")
def startup_event():
    """
    يتدرب الموديل مرة وحدة فقط عند بدء تشغيل السيرفر (وليس مع كل طلب).
    هذا يخلي كل طلب /simulate بعدها سريع جدًا (أقل من ثانية).
    """
    print("Training Prophet model... (يحدث مرة وحدة فقط عند التشغيل)")
    engine.train()
    print("Model ready.")


class SimulateRequest(BaseModel):
    forecast_months: int = Field(3, ge=1, le=MAX_FORECAST_MONTHS, description="عدد الأشهر المطلوب توقعها")
    decision_description: str = Field(..., description="وصف القرار، مثال: توظيف مهندس جديد")
    decision_type: Literal["Expense", "Income"] = "Expense"
    decision_behavior: Literal["Recurring", "One-time"] = "Recurring"
    decision_amount: float = Field(..., gt=0)
    safe_minimum_balance: float = Field(50000, ge=0)


@app.get("/health")
def health():
    return {"status": "ok", "model_ready": engine.forecast_full is not None}


@app.post("/simulate")
def simulate(payload: SimulateRequest):
    if engine.forecast_full is None:
        raise HTTPException(status_code=503, detail="الموديل لسا يتدرب، حاول بعد ثوانٍ")

    try:
        result = engine.simulate(
            forecast_months=payload.forecast_months,
            decision_description=payload.decision_description,
            decision_type=payload.decision_type,
            decision_behavior=payload.decision_behavior,
            decision_amount=payload.decision_amount,
            safe_minimum_balance=payload.safe_minimum_balance,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
