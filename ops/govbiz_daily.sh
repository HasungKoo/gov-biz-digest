#!/usr/bin/env bash
# 기업마당 공고 다이제스트 일일 실행.
#
# cron 이 --no-agent 로 호출한다. 표준출력이 그대로 기록에 남는다.
#
# 설계 원칙 (AGENTS.md 6장)
#   - 실패해도 exit 0 으로 끝내고 오류를 표준출력에 남긴다.
#     출력이 비면 "실패한 건지 잊은 건지" 알 수 없다.
#   - 단계별로 실패를 격리한다.
#   - Telegram 은 gateway 를 거치지 않고 직접 호출한다.
#
# 단계: 수집 -> 보고 -> Telegram -> HTML -> git push (Vercel 자동 배포)

PROJECT="$HOME/projects/gov-biz-digest"
PY="$PROJECT/.venv/bin/python"
REPORT="/tmp/govbiz_report_$$.txt"
SITE_URL="https://gov-biz-digest.vercel.app"
WITHIN="${GOVBIZ_WITHIN:-14}"
TOP="${GOVBIZ_TOP:-10}"

cleanup() { rm -f "$REPORT"; }
trap cleanup EXIT

echo "=== 기업마당 다이제스트 $(date '+%Y-%m-%d %H:%M:%S') ==="

cd "$PROJECT" 2>/dev/null || {
    echo "[중단] 프로젝트 폴더를 찾을 수 없습니다: $PROJECT"
    exit 0
}

if [ ! -x "$PY" ]; then
    echo "[중단] 가상환경 파이썬이 없습니다: $PY"
    exit 0
fi

# .env 읽기. 값에 공백이 있어도 안전하게.
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "[중단] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 가 없습니다."
    exit 0
fi

# ---------- 1. 수집 ----------
# 실패해도 멈추지 않는다. 마지막 저장분으로 보고를 시도한다.
echo "[1/5] 수집"
if "$PY" scripts/bizinfo_collect_once.py; then
    echo "[1/5] 수집 완료"
else
    echo "[1/5] 수집 실패. 마지막 저장분으로 보고를 시도합니다."
fi

# ---------- 2. 보고 생성 ----------
echo "[2/5] 보고 생성"
if ! "$PY" scripts/bizinfo_digest.py --within "$WITHIN" --top "$TOP" > "$REPORT" 2>&1; then
    echo "[2/5] 보고 생성 실패. 여기서 중단합니다."
    head -20 "$REPORT"
    exit 0
fi

LINES=$(wc -l < "$REPORT")
CHARS=$(wc -m < "$REPORT")
echo "[2/5] 보고 생성 완료 (${LINES}줄 ${CHARS}자)"

# ---------- 3. Telegram 전송 ----------
# 4096자 제한이 있다. 넘으면 3500자 단위로 잘라 보낸다.
echo "[3/5] Telegram 전송"

send_chunk() {
    local file="$1"
    local attempt
    for attempt in 1 2 3; do
        local res
        res=$(curl -s --max-time 30 -X POST \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text@${file}")
        if echo "$res" | grep -q '"ok":true'; then
            return 0
        fi
        echo "  전송 시도 ${attempt}/3 실패: $(echo "$res" | head -c 200)"
        sleep 10
    done
    return 1
}

SPLIT_DIR=$(mktemp -d)
if [ "$CHARS" -gt 3800 ]; then
    # 줄 단위로 자른다. 문장 중간이 끊기지 않게.
    split -C 3500 -d "$REPORT" "$SPLIT_DIR/part_"
    echo "  긴 보고라 $(ls "$SPLIT_DIR" | wc -l)개로 나눠 보냅니다."
else
    cp "$REPORT" "$SPLIT_DIR/part_00"
fi

FAILED=0
for part in "$SPLIT_DIR"/part_*; do
    if ! send_chunk "$part"; then
        FAILED=$((FAILED + 1))
    fi
    sleep 1
done
rm -rf "$SPLIT_DIR"

if [ "$FAILED" -eq 0 ]; then
    echo "[3/5] 전송 완료"
else
    echo "[3/5] 전송 실패 ${FAILED}건. 네트워크를 확인하세요."
    echo "      (노트북이 절전에서 막 깨어난 경우 자주 발생합니다)"
fi

# ---------- 4. HTML 생성 ----------
# 여기서 실패해도 Telegram 보고는 이미 나갔다. 경고만 남긴다.
echo "[4/5] HTML 생성"
if "$PY" scripts/bizinfo_report.py; then
    echo "[4/5] HTML 생성 완료"
else
    echo "[4/5] HTML 생성 실패. 웹페이지는 갱신되지 않습니다."
    echo "=== 종료 $(date '+%H:%M:%S') ==="
    exit 0
fi

# ---------- 5. git push ----------
echo "[5/5] 배포"
if [ -z "$(git status --porcelain docs/)" ]; then
    echo "[웹페이지] 변경 없음 · $SITE_URL"
    echo "=== 종료 $(date '+%H:%M:%S') ==="
    exit 0
fi

git add docs/
if ! git commit -q -m "chore: 웹페이지 자동 갱신 $(date '+%Y-%m-%d %H:%M')"; then
    echo "[웹페이지] 커밋 실패."
    echo "=== 종료 $(date '+%H:%M:%S') ==="
    exit 0
fi

if git push -q 2>&1; then
    echo "[웹페이지] 갱신 완료 · $SITE_URL"
else
    echo "[웹페이지] push 실패. git 인증을 확인하세요."
fi

echo "=== 종료 $(date '+%H:%M:%S') ==="
exit 0
