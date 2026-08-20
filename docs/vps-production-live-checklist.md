# VPS Production Live Trading Checklist

Follow this step-by-step checklist on the production VPS host before starting live trading.

---

## Phase 1: VPS Host Preparation
- [ ] Docker and Docker Compose installed (`docker compose version` >= 2.20)
- [ ] Repository cloned to VPS host
- [ ] Host firewall configured (allow port `8000` or configure reverse proxy with SSL)
- [ ] `.env` created from `.env.production.example` and secured (`chmod 600 .env`)

---

## Phase 2: Configuration & Preflight
- [ ] `COINDCX_API_KEY` and `COINDCX_API_SECRET` set in `.env`
- [ ] CoinDCX API key verified to have **TRADE** permission and **NO WITHDRAWAL** permission
- [ ] Optional: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set if Telegram alerts desired
- [ ] Risk limits confirmed (`MAX_TOTAL_CAPITAL`, `MAX_CAPITAL_PER_COIN`, `DAILY_LOSS_LIMIT`, `MIN_WALLET_BALANCE`)
- [ ] Run preflight validator:
  ```bash
  python grid-trading-bot/scripts/preflight.py
  ```
- [ ] Preflight result reports `RESULT: PASS`

---

## Phase 3: Container Launch & Dashboard Verification
- [ ] Start container:
  ```bash
  docker compose up --build -d
  ```
- [ ] Check logs for clean startup:
  ```bash
  docker compose logs -f
  ```
- [ ] Confirm `./data/grid_bot.db` is created and persistent
- [ ] Open Web Dashboard at `http://<VPS_IP>:8000`
- [ ] Verify Dashboard shows:
  - System Health: OK
  - Emergency Stop: Visible in Header
  - Active Grids: 0 (or restored grids)
  - Risk limits and configuration displayed accurately

---

## Phase 4: Phased Live Order Validation
> **CRITICAL RULE:** Do NOT enable automated trading until manual order verification is 100% complete.

- [ ] **Step 1:** Confirm Emergency Stop is ON during initial dashboard inspection
- [ ] **Step 2:** Turn Emergency Stop OFF via Dashboard header
- [ ] **Step 3:** Perform ONE small manual REAL order from the Web Dashboard
- [ ] **Step 4:** Verify the REAL LIVE-ORDER confirmation modal appears with accurate coin and INR value
- [ ] **Step 5:** Confirm fill on CoinDCX and verify trade appears in Dashboard Trade History
- [ ] **Step 6:** Only after verifying Step 5, start automated DCA grids

---

## Phase 5: Emergency Procedures
- [ ] Verify how to stop trading immediately:
  - Via Web Dashboard: Click `Emergency Stop: OFF` -> `ACTIVATE EMERGENCY STOP`
  - Via VPS command line: `docker compose stop`
  - Via Telegram (if configured): `/emergencystop`
