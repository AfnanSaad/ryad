# -*- coding: utf-8 -*-
"""
model.py
منطق التنبؤ المالي لمشروع "رياد" — منقول من riyad.py (Colab) وأُعيد تنظيمه كوحدة
قابلة للاستدعاء عبر API بدل ما يشتغل مرة وحدة من فوق لتحت في notebook.

الفكرة:
- generate_synthetic_data(): يبني نفس بيانات المعاملات الاصطناعية
- build_daily_net(): ينظف ويحسب صافي التدفق اليومي
- train_and_forecast(): يدرب Prophet مرة وحدة عند تشغيل السيرفر (startup)
  ويخزن التوقع لأقصى مدى زمني مدعوم، بدل ما يعيد التدريب كل طلب (بطيء).
- simulate_decision(): سريعة جدًا (عمليات حسابية بس) — تُستدعى مع كل طلب
  من Figma لتطبيق سيناريو "ماذا لو؟" على التوقع الجاهز.
"""

import numpy as np
import pandas as pd
from datetime import datetime
from prophet import Prophet

np.random.seed(42)

STARTING_BALANCE = 500000.0
MAX_FORECAST_MONTHS = 6          # أقصى مدى تدعمه الواجهة (لتفادي إعادة تدريب الموديل لكل طلب)
DAYS_PER_MONTH = 30


def generate_synthetic_data() -> pd.DataFrame:
    """نفس منطق توليد البيانات الاصطناعية من riyad.py بالضبط."""
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2024, 6, 30)
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D')

    balance = STARTING_BALANCE
    records = []

    project_dates = pd.to_datetime(np.sort(np.random.choice(all_dates, size=7, replace=False)))
    dataset_sale_dates = pd.to_datetime(np.sort(np.random.choice(all_dates, size=2, replace=False)))
    workshop_dates = pd.to_datetime(np.sort(np.random.choice(all_dates, size=5, replace=False)))

    SENIOR_BIWEEKLY = 18000
    JUNIOR_BIWEEKLY = 9750

    for date in all_dates:
        day_of_month = date.day
        ts = pd.Timestamp(date)

        if day_of_month == 1:
            months_passed = (date.year - start_date.year) * 12 + (date.month - start_date.month)
            licensing = max(np.random.normal(loc=20000 + months_passed * 1000, scale=1500), 0)
            balance += licensing
            records.append([date, round(licensing, 2), 'In', 'Model Licensing', round(balance, 2)])

        if ts in project_dates:
            revenue = max(np.random.normal(loc=85000, scale=25000), 30000)
            balance += revenue
            records.append([date, round(revenue, 2), 'In', 'Project Revenue', round(balance, 2)])

        if ts in dataset_sale_dates:
            dataset_income = max(np.random.normal(loc=60000, scale=15000), 40000)
            balance += dataset_income
            records.append([date, round(dataset_income, 2), 'In', 'Dataset Sale', round(balance, 2)])

        if ts in workshop_dates:
            workshop = max(np.random.normal(loc=18000, scale=4000), 8000)
            balance += workshop
            records.append([date, round(workshop, 2), 'In', 'Training Workshop', round(balance, 2)])

        if day_of_month in [1, 15]:
            senior_salary = max(np.random.normal(loc=SENIOR_BIWEEKLY, scale=400), 0)
            balance -= senior_salary
            records.append([date, -round(senior_salary, 2), 'Out', 'Senior Engineer Salary', round(balance, 2)])

        if day_of_month in [1, 15]:
            junior_salary = max(np.random.normal(loc=JUNIOR_BIWEEKLY, scale=300), 0)
            balance -= junior_salary
            records.append([date, -round(junior_salary, 2), 'Out', 'Junior Engineer Salary', round(balance, 2)])

        if np.random.rand() < 0.30:
            if np.random.rand() < 0.05:
                gpu = np.random.normal(loc=8000, scale=2000)
            else:
                gpu = np.random.normal(loc=900, scale=300)
            gpu = max(gpu, 0)
            balance -= gpu
            records.append([date, -round(gpu, 2), 'Out', 'GPU Rental', round(balance, 2)])

        if day_of_month == 1:
            rent = max(np.random.normal(loc=6500, scale=150), 0)
            balance -= rent
            records.append([date, -round(rent, 2), 'Out', 'Co-working Rent', round(balance, 2)])

        if day_of_month == 1:
            months_passed = (date.year - start_date.year) * 12 + (date.month - start_date.month)
            tools = max(np.random.normal(loc=3500 + months_passed * 80, scale=400), 0)
            balance -= tools
            records.append([date, -round(tools, 2), 'Out', 'Software & Tools Subscriptions', round(balance, 2)])

    df = pd.DataFrame(records, columns=['Date', 'Amount', 'Type', 'Category', 'Balance'])
    return df.sort_values('Date').reset_index(drop=True)


def build_daily_net(df: pd.DataFrame) -> pd.DataFrame:
    """تنظيف البيانات وتحويلها لصافي تدفق يومي (نفس منطق riyad.py)."""
    df_clean = df.copy()
    df_clean['Date'] = pd.to_datetime(df_clean['Date'], errors='coerce')
    df_clean = df_clean.dropna(subset=['Date'])
    df_clean = df_clean.drop_duplicates(keep='first')
    df_clean = df_clean.dropna(subset=['Amount'])
    df_clean['Category'] = df_clean['Category'].fillna('Uncategorized')
    df_clean = df_clean.sort_values('Date').reset_index(drop=True)

    daily_net = (
        df_clean.groupby('Date')['Amount']
        .sum()
        .reset_index()
        .rename(columns={'Amount': 'Net_Cash_Flow'})
    )

    full_range = pd.DataFrame({
        'Date': pd.date_range(start=df_clean['Date'].min(), end=df_clean['Date'].max(), freq='D')
    })
    daily_net = full_range.merge(daily_net, on='Date', how='left')
    daily_net['Net_Cash_Flow'] = daily_net['Net_Cash_Flow'].fillna(0)
    return daily_net


class ForecastEngine:
    """
    يُنشأ مرة وحدة عند تشغيل السيرفر (startup). يدرب Prophet على كامل
    التاريخ ويحسب أقصى توقع مطلوب (MAX_FORECAST_MONTHS)، ثم يخزنه في
    الذاكرة. كل طلب يجي بعدين يقتطع من هذا التوقع الجاهز بدل إعادة التدريب.
    """

    def __init__(self):
        self.daily_net = None
        self.current_balance = None
        self.forecast_full = None  # توقع لكل الأيام المستقبلية حتى أقصى مدى
        self.last_history_date = None

    def train(self):
        df = generate_synthetic_data()
        self.daily_net = build_daily_net(df)

        prophet_df = self.daily_net.rename(columns={'Date': 'ds', 'Net_Cash_Flow': 'y'})

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=0.15,
            seasonality_prior_scale=10,
        )
        model.fit(prophet_df)

        max_days = MAX_FORECAST_MONTHS * DAYS_PER_MONTH
        future = model.make_future_dataframe(periods=max_days)
        forecast = model.predict(future)

        self.last_history_date = prophet_df['ds'].max()
        future_only = forecast[forecast['ds'] > self.last_history_date][
            ['ds', 'yhat', 'yhat_lower', 'yhat_upper']
        ].reset_index(drop=True)

        historical_balance = self.daily_net.copy()
        historical_balance['Balance'] = STARTING_BALANCE + historical_balance['Net_Cash_Flow'].cumsum()
        self.current_balance = historical_balance['Balance'].iloc[-1]

        forecast_balance = future_only.copy().rename(columns={'ds': 'Date'})
        forecast_balance['Balance'] = self.current_balance + forecast_balance['yhat'].cumsum()

        daily_margin = (forecast_balance['yhat_upper'] - forecast_balance['yhat_lower']) / 2
        cumulative_sd = np.sqrt((daily_margin ** 2).cumsum())
        forecast_balance['Balance_Lower'] = forecast_balance['Balance'] - cumulative_sd
        forecast_balance['Balance_Upper'] = forecast_balance['Balance'] + cumulative_sd

        self.forecast_full = forecast_balance

    def simulate(
        self,
        forecast_months: int,
        decision_description: str,
        decision_type: str,       # "Expense" | "Income"
        decision_behavior: str,   # "Recurring" | "One-time"
        decision_amount: float,
        safe_minimum_balance: float,
    ) -> dict:
        if self.forecast_full is None:
            raise RuntimeError("الموديل لم يُدرَّب بعد — نادِ train() أولاً")

        forecast_months = max(1, min(forecast_months, MAX_FORECAST_MONTHS))
        horizon_days = forecast_months * DAYS_PER_MONTH

        window = self.forecast_full.iloc[:horizon_days].copy()
        window = window.rename(columns={'Balance': 'Baseline_Balance'})

        decision_start = window['Date'].min()
        sign = -1 if decision_type == "Expense" else 1
        days_since_start = (window['Date'] - decision_start).dt.days

        if decision_behavior == "Recurring":
            months_elapsed = np.where(days_since_start >= 0, (days_since_start // DAYS_PER_MONTH) + 1, 0)
            cumulative_effect = sign * months_elapsed * decision_amount
        else:
            cumulative_effect = np.where(days_since_start >= 0, sign * decision_amount, 0)

        window['Scenario_Balance'] = window['Baseline_Balance'] + cumulative_effect

        baseline_risk = window[window['Baseline_Balance'] <= safe_minimum_balance]
        scenario_risk = window[window['Scenario_Balance'] <= safe_minimum_balance]

        risk_info = {
            "baseline_risk_date": baseline_risk['Date'].iloc[0].strftime('%Y-%m-%d') if len(baseline_risk) else None,
            "scenario_risk_date": scenario_risk['Date'].iloc[0].strftime('%Y-%m-%d') if len(scenario_risk) else None,
            "deficit_amount": None,
            "is_safe": len(scenario_risk) == 0,
        }
        if len(scenario_risk):
            risk_info["deficit_amount"] = round(
                float(safe_minimum_balance - scenario_risk['Scenario_Balance'].iloc[0]), 2
            )

        return {
            "current_balance": round(float(self.current_balance), 2),
            "safe_minimum_balance": safe_minimum_balance,
            "decision_description": decision_description,
            "forecast_months": forecast_months,
            "risk": risk_info,
            "series": [
                {
                    "date": row.Date.strftime('%Y-%m-%d'),
                    "baseline_balance": round(float(row.Baseline_Balance), 2),
                    "scenario_balance": round(float(row.Scenario_Balance), 2),
                }
                for row in window.itertuples()
            ],
        }
