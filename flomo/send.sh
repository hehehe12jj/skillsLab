#!/usr/bin/env bash
# Send a note to flomo via webhook.
# Usage:
#   echo "内容" | ~/.claude/skills/flomo/send.sh
#   ~/.claude/skills/flomo/send.sh "内容"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/.config"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config not found at $CONFIG" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$CONFIG"

if [[ -z "${FLOMO_WEBHOOK:-}" ]]; then
  echo "ERROR: FLOMO_WEBHOOK not set in $CONFIG" >&2
  exit 2
fi

if [[ $# -gt 0 ]]; then
  CONTENT="$*"
else
  CONTENT="$(cat)"
fi

if [[ -z "$CONTENT" ]]; then
  echo "ERROR: empty content" >&2
  exit 3
fi

# Build JSON with jq to escape properly.
PAYLOAD="$(jq -n --arg c "$CONTENT" '{content: $c, content_type: "markdown"}')"

RESPONSE="$(curl -sS -X POST "$FLOMO_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -w "\n__HTTP_STATUS__:%{http_code}")"

STATUS="$(printf '%s' "$RESPONSE" | tail -n1 | sed 's/^__HTTP_STATUS__://')"
BODY="$(printf '%s' "$RESPONSE" | sed '$d')"

if [[ "$STATUS" == "200" ]] && printf '%s' "$BODY" | grep -q '"code":0'; then
  echo "OK: flomo accepted the note (HTTP $STATUS)"
  echo "$BODY"
  exit 0
else
  echo "FAIL (HTTP $STATUS)" >&2
  echo "$BODY" >&2
  exit 1
fi
