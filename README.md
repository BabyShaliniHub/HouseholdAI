# HouseholdAI

**AI-Powered Early Warning System for Household Problems.** Learn. Detect. Explain. Warn.

HouseholdAI learns the normal rhythm of each home from its electricity and water-flow data and highlights unusual behaviour before it becomes a bigger problem.

> **Scope.** HouseholdAI performs anomaly detection and early warning. It does **not** diagnose physical faults, confirm leaks or predict appliance failure, and it makes no accuracy guarantees. Water alerts say "possible abnormal water flow", never "leak detected".

## Problem and solution

Households rarely notice a tap left running, a failing appliance or an odd night-time load until a bill arrives. Fixed thresholds ("alert above 5000 W") fail because every home is different. HouseholdAI instead learns each household's own baseline, scores how unusual each observation is, turns that into a risk level, and explains the reason in plain language.

## Features

- Household Pulse: a signature waveform (electricity above the line, water flow below) with clickable warning markers
- AI Risk Index (0-100) with NORMAL / LOW / MEDIUM / HIGH levels
- Plain-language explanations and recommended actions for every warning
- Early Warning Center timeline with level and household filters
- Household profile: normal electricity range, water behaviour, active hours, risk trend
- Data explorer: date range, resource switch, period comparison, household comparison, raw data under "View Data"
- AI insights computed from the results (nothing hand-written)
- Demo mode: a guided tour whose targets are chosen from the real model output
- Loading, empty, invalid-household, API-down and "ML results missing" states; light/dark theme; keyboard accessible; reduced-motion aware

## Architecture

```
data/processed/household_final_10000.csv
        |  ml/pipeline.py
        v
data/results/predictions.csv + model_report.json + isolation_forest.joblib
        |  backend/ (FastAPI, read-only)
        v
frontend/ (React + TypeScript + Vite)  <--  nginx proxies /api in Docker
```

## Dataset

`household_final_10000.csv`, derived from the hihAigua residential dataset: 10 households x 1,000 observations over 2025. Columns: `installation, ts_dt, powerW, volumeFlow, hour, day_of_week, month, is_weekend`.

- `powerW` is the electricity signal.
- `volumeFlow` is the water-flow signal (the old `volume` column is not used).
- The processed file has **no temperature column**. The pipeline uses temperature automatically if one is present; otherwise the UI states that it is not recorded.

Only this file is read. Earlier experiment outputs (`household_anomaly_results*.csv`, `detected_anomalies.csv`) are not used anywhere.

## AI / ML methodology

1. **Preprocessing**: validate columns, sort by household and time.
2. **Household-aware normalisation**: for each household, `powerW` and `volumeFlow` are log-transformed and converted to robust z-scores (median and MAD; standard deviation as fallback for zero-inflated water flow). A household that simply uses more is not anomalous.
3. **Feature engineering** (18 features): level vs household, deviation from that household's typical value *for the same hour*, change vs the previous observation, rolling mean/std (6 observations), time gap, cyclical hour/day/month encodings, weekend flag.
4. **Isolation Forest** (400 trees, seed 42) learns which feature combinations are easy to isolate.
5. **Calibrated anomaly boundary**: `contamination` is deliberately *not* used to label data (a fixed value imposes a percentage; `"auto"` flagged 28% in an earlier experiment). The score `-score_samples` is thresholded at Tukey's upper fence, `Q3 + 1.5 x IQR`. The anomaly share is therefore a result of the data, reported in `model_report.json`. `FENCE_K` in `ml/pipeline.py` controls strictness.

### Risk scoring

Separate from the model. For flagged observations the index is `40 + 60 x (0.40 score margin + 0.30 magnitude of deviation + 0.15 recent change + 0.15 persistence)`. LOW below 55, MEDIUM below 70, HIGH from 70. Unflagged observations score 0-39 and are NORMAL. Persistence counts how many of the previous 4 observations (not fixed time spans, since sampling may be irregular) already deviated in the same resource.

### Explainability

Explanations are generated from the numbers behind each warning: above/below household pattern, unusual for this hour (with the household's typical value), sharp change, persistence. The Isolation Forest score appears only under "AI analysis details".

## Tech stack

React, TypeScript, Vite (hand-built SVG charts, no chart library); FastAPI; pandas, numpy, scikit-learn; Docker Compose with nginx. PostgreSQL is not used: results are a read-only CSV produced by the pipeline, so a database would add moving parts without benefit.

## Project structure

```
ml/pipeline.py            data -> features -> model -> risk -> explanations
backend/app/              main.py (routes), schemas.py, insights.py
frontend/src/             App.tsx, views/, components/, lib/
data/processed/           household_final_10000.csv (you provide, not committed)
data/results/             generated by the pipeline
docker-compose.yml  .env.example
```

## Local setup

Place `household_final_10000.csv` in `data/processed/`.

```bash
python -m venv .venv && .venv\Scripts\activate        # Windows (use source .venv/bin/activate elsewhere)
pip install -r backend/requirements.txt
python -m ml.pipeline                                  # writes data/results/*
uvicorn backend.app.main:app --reload                  # http://localhost:8000/docs

cd frontend && npm install && npm run dev              # http://localhost:5173
```

`npm run typecheck` runs the TypeScript checker.

## Docker setup

```bash
cp .env.example .env        # copy .env.example .env on Windows
docker compose up --build   # open http://localhost:8080
```

The backend container runs the ML pipeline on start if `data/results/predictions.csv` is missing (`FORCE_RETRAIN=1` in `.env` re-runs it). `./data` is mounted into the container. nginx proxies `/api` to the `backend` service, so no `localhost` is assumed between containers. No secrets are required.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | status and whether ML results exist |
| `GET /api/households` | list with latest risk and warning counts |
| `GET /api/households/{id}/summary` | latest observation, risk, explanation, latest warning |
| `GET /api/households/{id}/electricity` , `/water` | series with baseline and anomaly flags (`start`, `end`) |
| `GET /api/households/{id}/anomalies` | warnings (`levels`, `start`, `end`) |
| `GET /api/households/{id}/risk` | risk index history |
| `GET /api/households/{id}/profile` | learned normal behaviour, trend, recent warnings |
| `GET /api/alerts` | warning feed (`household`, `levels`, `limit`) |
| `GET /api/anomalies/{id}` | full detail for one observation |
| `GET /api/insights` | insights (`household` optional) |
| `GET /api/compare` | per-household comparison |
| `GET /api/demo` | demo targets chosen from real results |
| `GET /api/model` | pipeline report (threshold, rates, features) |

### `/api/v1` (read-only view of the frozen ML output)

Reads `data/results/predictions.csv` (override with `HOUSEHOLDAI_PREDICTIONS_PATH`). Errors are JSON: `{"error": "...", "message": "..."}`.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | `{"status": "UP"}` |
| `GET /api/v1/dashboard/summary` | counts and percentages computed from the CSV |
| `GET /api/v1/warnings` | rows with `is_warning`, sorted by `risk_score` then time (`installation`, `risk_level`, `limit` optional) |
| `GET /api/v1/warnings/{id}` | one warning (`id` = `anomaly_id`); 404 if unknown |
| `GET /api/v1/households` | one summary per installation |
| `GET /api/v1/households/{installation}` | summary, recent warnings, recent statistical anomalies; 404 if unknown |

`risk_score` is the `risk_index` column. The older `/api/*` routes are unchanged.

Interactive docs at `/docs` when the backend runs.

## Screenshots
<img width="540" height="700" alt="Screenshot 2026-10-10 205817" src="https://github.com/user-attachments/assets/4e18efde-0f3d-4eb6-b1f3-ceecaf81ee97" />


## Future enhancements

Live data ingestion, per-household model retraining schedules, notifications, labelled feedback ("this was expected") to refine the boundary, appliance-level data, and tests against labelled incidents.
