#!/bin/sh
# Rebuild ML results when they are missing (or when FORCE_RETRAIN=1), then start the API.
set -e
RESULTS="${HOUSEHOLDAI_RESULTS:-/app/data/results}"
if [ "${FORCE_RETRAIN:-0}" = "1" ] || [ ! -f "$RESULTS/predictions.csv" ]; then
  echo "Running ML pipeline on ${HOUSEHOLDAI_DATA:-/app/data/processed/household_final_10000.csv}"
  python -m ml.pipeline > /dev/null
fi
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
