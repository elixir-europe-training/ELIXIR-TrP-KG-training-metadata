#!/usr/bin/env bash
# Report a failure of the weekly update as a GitHub issue labelled harvest-failure, which starts the
# fix-harvest workflow. If an open issue already has the same fingerprint, comment on it instead.
# Usage: scripts/report-failure.sh <fingerprint> <title> <log file> [<body file>]
#
# Authenticates as the elixir-trainer-harvest GitHub App, with its private key at GITHUB_APP_PRIVATE_KEY_PATH in .env
# (and GITHUB_APP_ID to use another App), see README for the setup.
# Requires curl, jq and openssl.
set -euo pipefail
cd "$(dirname "$0")/.."
fingerprint="$1"
title="$2"
log_file="$3"
body_file="${4:-}"

# Read a variable from .env without sourcing it
env_value() { { grep -E "^$1=" .env 2>/dev/null || true; } | tail -n 1 | cut -d= -f2- | sed -E "s/^['\"]//; s/['\"]$//"; }
repo="$(env_value GITHUB_REPO)"
repo="${repo:-elixir-europe-training/ELIXIR-trainer}"
# The App ID is public, only the private key is secret
app_id="$(env_value GITHUB_APP_ID)"
app_id="${app_id:-5730005}"
private_key="$(env_value GITHUB_APP_PRIVATE_KEY_PATH)"
api="https://api.github.com"
if [ ! -f "$private_key" ]; then
  echo "Can not report \"$title\" on GitHub: set GITHUB_APP_PRIVATE_KEY_PATH in .env" >&2
  exit 1
fi

# Sign a JWT with the App private key, then exchange it for an installation token valid 1 hour
github_token() {
  b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }
  local now header payload signature jwt installation
  now=$(date +%s)
  header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
  payload=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
  signature=$(printf '%s.%s' "$header" "$payload" \
    | openssl dgst -sha256 -sign "$private_key" -binary | b64url)
  jwt="$header.$payload.$signature"
  # errexit does not apply in command substitutions, so each failure is checked explicitly
  installation=$(curl -sSf -H "Authorization: Bearer $jwt" "$api/repos/$repo/installation" | jq -r .id) || {
    echo "Can not find the installation of the GitHub App $app_id on $repo: check that the App is installed on" \
      "this repository (404), and that the private key belongs to this App (401)" >&2
    return 1
  }
  curl -sSf -X POST -H "Authorization: Bearer $jwt" "$api/app/installations/$installation/access_tokens" \
    | jq -r .token || { echo "Can not get an installation token of the GitHub App $app_id" >&2; return 1; }
}
token="$(github_token)" || exit 1
gh_api() { curl -sSf -H "Authorization: Bearer $token" -H "Accept: application/vnd.github+json" "$@"; }

# Issue body: the fingerprint (hidden, used for deduplication), the details, and the end of the log.
# The repository is public: the log must not contain secrets
details=""
if [ -n "$body_file" ]; then details="$(cat "$body_file")"; fi
body="<!-- harvest-fingerprint: $fingerprint -->
Reported by \`scripts/weekly-update.sh\` on $(date '+%Y-%m-%d %H:%M:%S %Z').

$details

<details><summary>End of the log</summary>

\`\`\`
$(tail -n 100 "$log_file" | cut -c 1-500)
\`\`\`
</details>"
# GitHub limits bodies to 65536 characters
body="${body:0:60000}"

existing=$(gh_api "$api/repos/$repo/issues?state=open&labels=harvest-failure&per_page=100" \
  | jq -r --arg fp "harvest-fingerprint: $fingerprint" '[.[] | select(.body // "" | contains($fp))][0].number // empty')
if [ -n "$existing" ]; then
  gh_api -X POST "$api/repos/$repo/issues/$existing/comments" \
    -d "$(jq -n --arg body "Failed again.

$body" '{body: $body}')" >/dev/null
  echo "Commented on the existing issue https://github.com/$repo/issues/$existing"
else
  url=$(gh_api -X POST "$api/repos/$repo/issues" \
    -d "$(jq -n --arg title "$title" --arg body "$body" '{title: $title, body: $body, labels: ["harvest-failure"]}')" \
    | jq -r .html_url)
  echo "Created the issue $url"
fi
