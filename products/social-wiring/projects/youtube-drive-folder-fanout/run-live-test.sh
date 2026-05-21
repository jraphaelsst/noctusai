#!/usr/bin/env bash
# Live test for youtube-drive-folder-fanout against the running container.
#
# Auth: uses the new ApiToken shape from platform-auth-modernization
# (`Authorization: Bearer pk_*`). No human-user JWT involved. The token
# represents an automation caller (n8n / MCP / agent live-test), not a
# user identity.
#
# Usage:
#   export SOCIAL_WIRING_API_TOKEN="pk_<your-token>"
#   export SOCIAL_WIRING_ORG_ID="<uuid>"   # the org this token belongs to
#   bash products/social-wiring/projects/youtube-drive-folder-fanout/run-live-test.sh
#
# What it does:
#   1. POST /api/videos/upload/drive-folder with product_code=ONE10010 and the
#      Drive folder URL provided by the operator. Server-side enriches via
#      seed Vista CRM → build_youtube_metadata → fans out one job per video.
#   2. Polls /api/videos/upload/batch/<batch_id> every 5s up to 25 min,
#      printing a one-liner per iteration ("3/5 published; 1 uploading; ...").
#   3. Exits 0 when every child reaches a terminal state (published/notified/
#      failed), 1 on any failure shape.

set -euo pipefail

HOST="${HOST:-http://localhost:8011}"
DRIVE_FOLDER="${DRIVE_FOLDER:-https://drive.google.com/drive/folders/1y8Dr_q0xE13q3dHPrBPef-Bl9H76guni?usp=drive_link}"
PRODUCT_CODE="${PRODUCT_CODE:-ONE10010}"

if [[ -z "${SOCIAL_WIRING_API_TOKEN:-}" ]]; then
    cat <<'HELP' >&2
SOCIAL_WIRING_API_TOKEN not set.

HOW TO GET AN API TOKEN:

(A) Via the Settings UI (post-FE-migration):
    Settings → API Tokens → Create new → copy the `pk_*` value shown ONCE.
    (Re-shown only at creation time — the rest of the time only the prefix
    is visible, by design.)

(B) Direct DB insert for v1 / pre-FE-migration testing
    (architect uses Supabase MCP execute_sql):
    INSERT INTO social_wiring.api_tokens (org_id, label, token_hash, token_prefix)
    VALUES ('<your-org-uuid>', 'agent-live-test',
            encode(sha256('pk_<your-chosen-secret>'::bytea), 'hex'),
            'pk_<first-8-chars>')
    RETURNING id;

Then:
    export SOCIAL_WIRING_API_TOKEN="pk_<your-chosen-secret>"
    export SOCIAL_WIRING_ORG_ID="<your-org-uuid>"
    bash products/social-wiring/projects/youtube-drive-folder-fanout/run-live-test.sh
HELP
    exit 1
fi

if [[ -z "${SOCIAL_WIRING_ORG_ID:-}" ]]; then
    echo "SOCIAL_WIRING_ORG_ID not set — required for product-token requests." >&2
    exit 1
fi

echo "==> Posting fan-out request (product_code=$PRODUCT_CODE)..."
RESP=$(curl -sS -X POST "$HOST/api/videos/upload/drive-folder" \
    -H "Authorization: Bearer $SOCIAL_WIRING_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"drive_folder_url\": \"$DRIVE_FOLDER\",
        \"product_code\": \"$PRODUCT_CODE\",
        \"privacy_status\": \"unlisted\"
    }")

echo "Response: $RESP"

BATCH_ID=$(echo "$RESP" | jq -r '.batch_id // empty')
if [[ -z "$BATCH_ID" || "$BATCH_ID" == "null" ]]; then
    echo "ERROR: no batch_id in response — auth or schema-validation failure" >&2
    exit 1
fi

echo "==> Batch id: $BATCH_ID"
echo "==> Polling batch status every 5s..."

for i in {1..300}; do
    STATUS=$(curl -sS "$HOST/api/videos/upload/batch/$BATCH_ID" \
        -H "Authorization: Bearer $SOCIAL_WIRING_API_TOKEN" \
        -H "X-Org-Id: $SOCIAL_WIRING_ORG_ID")

    TOTAL=$(echo "$STATUS" | jq -r .total)
    PUB=$(echo "$STATUS" | jq -r .counts.published)
    NOT=$(echo "$STATUS" | jq -r .counts.notified)
    FAIL=$(echo "$STATUS" | jq -r .counts.failed)
    UP=$(echo "$STATUS" | jq -r .counts.uploading)
    DL=$(echo "$STATUS" | jq -r .counts.downloading)
    PR=$(echo "$STATUS" | jq -r .counts.processing)
    QU=$(echo "$STATUS" | jq -r .counts.queued)
    TERMINAL=$((PUB + NOT + FAIL))

    printf "[t=%3dx5s] total=%s published=%s notified=%s failed=%s uploading=%s processing=%s downloading=%s queued=%s\n" \
        "$i" "$TOTAL" "$PUB" "$NOT" "$FAIL" "$UP" "$PR" "$DL" "$QU"

    if [[ "$TERMINAL" == "$TOTAL" ]]; then
        echo "==> All jobs reached a terminal state."
        echo "==> Final per-job summary:"
        echo "$STATUS" | jq -r '.jobs[] | "  - \(.id) | \(.status) | target=\(.target_format) | file=\(.file_name) | yt=\(.youtube_video_id) | err=\(.error_message)"'
        if [[ "$FAIL" -gt 0 ]]; then
            exit 1
        fi
        exit 0
    fi

    sleep 5
done

echo "==> 25min timeout — not every job reached terminal state."
exit 2
