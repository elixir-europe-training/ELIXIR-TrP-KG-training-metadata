#!/usr/bin/env bash
# Weekly update of the knowledge graph, run by cron on the server (see README):
# pull the latest code, harvest the sources, build a new Qlever index while the current one keeps serving,
# swap it in (rolling back if Qlever does not start), reload the VoID and examples graphs, and redeploy the API.
# Each failure is reported as a GitHub issue by scripts/report-failure.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Log of this run, its tail is attached to the issues. Set up once, before the script restarts itself
if [ -z "${UPDATE_LOG:-}" ]; then
  mkdir -p logs
  UPDATE_LOG="logs/weekly-update-$(date +%F).log"
  export UPDATE_LOG
  exec > >(tee -a "$UPDATE_LOG") 2>&1
fi
LOG="$UPDATE_LOG"

step="start"
# Report any unexpected failure with the step it happened in, the end of the log, and stop
trap 'scripts/report-failure.sh "step-$step" "Weekly update failed at step $step" "$LOG"' ERR

# Pull the latest code (fixes merged in main), then restart from the pulled version of this script
if [ "${1:-}" != "--pulled" ]; then
  echo "=== Weekly update started $(date '+%Y-%m-%d %H:%M:%S %Z')"
  step="git-pull"
  git pull --ff-only
  exec "$0" --pulled
fi

step="build"
docker compose --profile jobs build harvest api

# A failing source keeps its previous data, the others are still updated, the failures are reported at the end
step="harvest"
harvest_failed=false
docker compose --profile jobs run --rm harvest || harvest_failed=true

# The new index is built in /index/next while Qlever keeps serving the current one
step="index-build"
docker compose run --rm --no-deps -e INDEX_STEPS=build index

# Only downtime of the update: stop Qlever, swap the indexes, start Qlever and wait for its healthcheck
step="index-swap"
docker compose stop qlever
docker compose run --rm --no-deps -e INDEX_STEPS=swap index
if ! docker compose up -d --no-deps --wait qlever; then
  step="index-rollback"
  docker compose stop qlever
  docker compose run --rm --no-deps -e INDEX_STEPS=rollback index
  docker compose up -d --no-deps --wait qlever
  scripts/report-failure.sh "step-qlever-start" "Qlever did not start with the new index, rolled back to the previous one" "$LOG"
  exit 1
fi

step="generate-metadata"
docker compose run --rm --no-deps generate-metadata

# Recreated to deploy the pulled code, and to reindex the VoID classes and examples it loads at startup
step="api"
docker compose up -d --no-deps --force-recreate --wait --wait-timeout 1200 api

step="report-harvest"
if [ "$harvest_failed" = true ]; then
  if [ -f data/harvest-failures.json ]; then
    # One issue per failed source, deduplicated by the fingerprint of the failure
    jq -c '.[]' data/harvest-failures.json | while read -r failure; do
      body_file=$(mktemp)
      jq -r '"**Error:** `\(.error)`\n\n```\n\(.traceback)\n```"' <<<"$failure" >"$body_file"
      scripts/report-failure.sh "$(jq -r .fingerprint <<<"$failure")" \
        "Harvest of $(jq -r .source <<<"$failure") failed" "$LOG" "$body_file"
      rm -f "$body_file"
    done
  else
    # The harvest container failed before writing its report (image, out of memory...)
    scripts/report-failure.sh "step-harvest" "Harvest container failed" "$LOG"
  fi
  exit 1
fi
echo "=== Weekly update done $(date '+%Y-%m-%d %H:%M:%S %Z')"
