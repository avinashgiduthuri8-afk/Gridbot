#!/usr/bin/env bash
# live_preflight_check.sh — run this immediately before starting your
# first live-mode grid (or any time after a code change, before trusting
# real capital to it again). Fails loudly (exit 1) on the first check that
# looks unsafe, rather than continuing past a red flag.
#
# Usage:
#   cd grid-trading-bot
#   bash scripts/live_preflight_check.sh
#
# On Windows, run this from Git Bash (comes with Git for Windows) —
# Command Prompt / PowerShell can't run .sh scripts directly.

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILURES=0
WARNINGS=0

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗ $1${NC}"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "  ${YELLOW}! $1${NC}"; WARNINGS=$((WARNINGS + 1)); }

echo "=================================================="
echo " Gridbot — LIVE TRADING pre-flight check"
echo "=================================================="

# ---------------------------------------------------------------
# 1. Working tree must be clean and tests must pass. Never go live
#    on top of uncommitted or untested changes.
# ---------------------------------------------------------------
echo ""
echo "[1/7] Git state"
if git diff --quiet && git diff --cached --quiet; then
    pass "Working tree is clean (no uncommitted changes)"
else
    fail "Uncommitted changes present — commit or stash before going live"
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
if [ "$CURRENT_BRANCH" = "main" ]; then
    pass "On main branch"
else
    warn "Not on main branch (currently: $CURRENT_BRANCH) — confirm this is intentional"
fi

echo ""
echo "[2/7] Test suite"
if command -v python3 >/dev/null 2>&1; then
    PYCMD=python3
elif command -v python >/dev/null 2>&1; then
    PYCMD=python
else
    fail "No python/python3 found on PATH — cannot run tests"
    PYCMD=""
fi

if [ -n "$PYCMD" ]; then
    if $PYCMD -m pytest -q > /tmp/preflight_pytest.log 2>&1; then
        RESULT=$(tail -1 /tmp/preflight_pytest.log)
        pass "Full test suite passes ($RESULT)"
    else
        fail "Test suite FAILED — see /tmp/preflight_pytest.log. Do not go live."
        tail -20 /tmp/preflight_pytest.log | sed 's/^/      /'
    fi
fi

# ---------------------------------------------------------------
# 3. Env file sanity — real API credentials present, look like real
#    values rather than leftover placeholders/fakes.
# ---------------------------------------------------------------
echo ""
echo "[3/7] Environment configuration"
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    fail "$ENV_FILE not found — cannot check credentials"
else
    for VAR in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID COINDCX_API_KEY COINDCX_API_SECRET; do
        VALUE=$(grep -E "^${VAR}=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
        if [ -z "$VALUE" ]; then
            fail "$VAR is empty in $ENV_FILE"
        elif echo "$VALUE" | grep -qiE "fake|test|xxx|changeme|your_|placeholder"; then
            fail "$VAR looks like a placeholder value: ${VALUE:0:12}..."
        else
            pass "$VAR is set (${#VALUE} chars)"
        fi
    done

    WEBHOOK_ENABLED=$(grep -E "^WEBHOOK_ENABLED=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
    if [ "$WEBHOOK_ENABLED" = "true" ]; then
        warn "WEBHOOK_ENABLED=true — this bot's webhook signature/payload format is UNVERIFIED against CoinDCX's real docs (see webhooks/server.py docstring). Consider leaving this off until confirmed."
    else
        pass "WEBHOOK_ENABLED is off (or unset) — polling-only, the verified path"
    fi
fi

# ---------------------------------------------------------------
# 4. Emergency stop must be OFF before you expect trading to work,
#    but you should also know how to turn it ON in a hurry.
# ---------------------------------------------------------------
echo ""
echo "[4/7] Emergency stop state"
DB_PATH=$(grep -E "^DATABASE_PATH=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
DB_PATH=${DB_PATH:-data/grid_bot.db}
if [ -f "$DB_PATH" ] && command -v sqlite3 >/dev/null 2>&1; then
    ESTOP=$(sqlite3 "$DB_PATH" "SELECT value FROM monitor_settings WHERE key='emergency_stop';" 2>/dev/null)
    if [ "$ESTOP" = "1" ] || [ "$ESTOP" = "true" ]; then
        warn "Emergency stop is currently ACTIVE — trading is blocked until you run /clearemergency in Telegram. (This may be intentional.)"
    else
        pass "Emergency stop is not active"
    fi
    echo "      Reminder: /emergencystop in Telegram halts all trading instantly if something looks wrong."
else
    warn "Could not check emergency-stop state (sqlite3 not found, or DB doesn't exist yet — fine on first-ever run)"
fi

# ---------------------------------------------------------------
# 5. Confirm no grid is silently in the wrong mode.
# ---------------------------------------------------------------
echo ""
echo "[5/7] Active grid modes"
if [ -f "$DB_PATH" ] && command -v sqlite3 >/dev/null 2>&1; then
    GRIDS=$(sqlite3 -separator ' | ' "$DB_PATH" \
        "SELECT grid_id, symbol, mode, status FROM dca_grids WHERE status='active';" 2>/dev/null)
    if [ -z "$GRIDS" ]; then
        pass "No active grids — clean slate"
    else
        echo "      Active grids right now:"
        echo "$GRIDS" | sed 's/^/        /'
        echo "      -> Confirm every 'real' row above is one you intend to run with real money,"
        echo "         and every 'paper' row is one you're OK NOT trading for real."
    fi
else
    warn "Could not list active grids"
fi

# ---------------------------------------------------------------
# 6. Capital / risk limits are actually configured, not defaulted
#    to something absurd.
# ---------------------------------------------------------------
echo ""
echo "[6/7] Risk limits configured"
if [ -f "$ENV_FILE" ]; then
    for VAR in MAX_TOTAL_CAPITAL MAX_CAPITAL_PER_COIN MAX_SIMULTANEOUS_GRIDS DAILY_LOSS_LIMIT; do
        VALUE=$(grep -E "^${VAR}=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
        if [ -z "$VALUE" ]; then
            warn "$VAR not set in .env — config/settings.py default will apply, confirm that's intentional"
        else
            pass "$VAR = $VALUE"
        fi
    done
fi

# ---------------------------------------------------------------
# 7. Final human checklist — things no script can verify.
# ---------------------------------------------------------------
echo ""
echo "[7/7] Manual checklist (cannot be automated — confirm yourself)"
echo "      [ ] CoinDCX API key permissions checked (trade only, NOT withdrawal)"
echo "      [ ] Starting with a small real amount (e.g. ₹500-1000), not full capital"
echo "      [ ] You are watching Telegram + logs live for the first hour, not walking away"
echo "      [ ] You know the /emergencystop command and have tested it once in paper mode"
echo "      [ ] Railway service is on a persistent volume, not ephemeral storage"

echo ""
echo "=================================================="
if [ "$FAILURES" -gt 0 ]; then
    echo -e " ${RED}RESULT: $FAILURES failure(s), $WARNINGS warning(s) — DO NOT GO LIVE${NC}"
    echo "=================================================="
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    echo -e " ${YELLOW}RESULT: 0 failures, $WARNINGS warning(s) — review warnings above${NC}"
    echo "=================================================="
    exit 0
else
    echo -e " ${GREEN}RESULT: All automated checks passed${NC}"
    echo " Automated checks are necessary, not sufficient — still work"
    echo " through the manual checklist in [7/7] before going live."
    echo "=================================================="
    exit 0
fi
