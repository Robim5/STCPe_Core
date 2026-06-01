#!/usr/bin/env sh
# exemplo para cron-job.org, crontab ou CI.
# uso: BASE_URL=https://... CRON_SECRET=... sh scripts/cron_refresh.example.sh

set -eu

BASE_URL="${BASE_URL:?define BASE_URL}"
CRON_SECRET="${CRON_SECRET:?define CRON_SECRET}"

curl -fsS -H "Authorization: Bearer ${CRON_SECRET}" \
  "${BASE_URL%/}/api/internal/refresh"
