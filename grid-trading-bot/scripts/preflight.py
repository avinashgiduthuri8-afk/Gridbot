"""Production Preflight Validator for GridBot (VPS / Docker Deployment).

Validates all required secrets, risk limits, database write permissions,
and operational configurations without executing trades or exposing secrets.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def mask_status(val: str | None) -> str:
    if val and val.strip():
        return "SET"
    return "MISSING"


def run_preflight() -> bool:
    print("=========================================")
    print("      GridBot Production Preflight       ")
    print("=========================================\n")

    errors: list[str] = []

    # 1. Environment & Secrets Check
    print("--- Environment & Secrets ---")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    cdx_key = os.getenv("COINDCX_API_KEY", "").strip()
    cdx_secret = os.getenv("COINDCX_API_SECRET", "").strip()

    if tg_token and tg_chat:
        print(f"TELEGRAM_BOT_TOKEN ..... {mask_status(tg_token)}")
        print(f"TELEGRAM_CHAT_ID ....... {mask_status(tg_chat)}")
    else:
        print("TELEGRAM ............... OPTIONAL (Not configured - Web Dashboard mode)")

    print(f"COINDCX_API_KEY ........ {mask_status(cdx_key)}")
    print(f"COINDCX_API_SECRET ..... {mask_status(cdx_secret)}")

    if not cdx_key:
        errors.append("COINDCX_API_KEY is required for live trading.")
    if not cdx_secret:
        errors.append("COINDCX_API_SECRET is required for live trading.")

    if not errors:
        print("[PASS] All required exchange credentials present.\n")
    else:
        print("[FAIL] Missing required exchange credentials.\n")

    # 2. Database Path & Directory Permissions
    print("--- Database Path & Persistence ---")
    db_path = os.getenv("DATABASE_PATH", "data/grid_bot.db").strip()
    db_abs = os.path.abspath(db_path)
    print(f"DATABASE_PATH .......... {db_path} -> {db_abs}")

    db_dir = os.path.dirname(db_abs)
    if not db_dir:
        db_dir = "."

    if os.path.exists(db_dir):
        print(f"Database Directory ..... PASS ({db_dir})")
    else:
        try:
            os.makedirs(db_dir, exist_ok=True)
            print(f"Database Directory ..... CREATED ({db_dir})")
        except Exception as exc:
            errors.append(f"Failed to create database directory {db_dir}: {exc}")
            print(f"Database Directory ..... FAIL ({db_dir})")

    # Check write access
    test_file = os.path.join(db_dir, ".preflight_write_test")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        print(f"Database Writable ...... PASS ({db_dir})\n")
    except Exception as exc:
        errors.append(f"Database directory {db_dir} is not writable: {exc}")
        print(f"Database Writable ...... FAIL ({db_dir})\n")

    # 3. Risk Configuration Check
    print("--- Configuration Validation ---")
    try:
        max_total_cap = float(os.getenv("MAX_TOTAL_CAPITAL", "50000"))
        max_coin_cap = float(os.getenv("MAX_CAPITAL_PER_COIN", "20000"))
        max_grids = int(os.getenv("MAX_SIMULTANEOUS_GRIDS", "20"))
        min_wallet = float(os.getenv("MIN_WALLET_BALANCE", "500"))
        daily_loss = float(os.getenv("DAILY_LOSS_LIMIT", "2000"))

        if max_total_cap < 0 or max_coin_cap < 0 or max_grids < 1 or min_wallet < 0 or daily_loss < 0:
            errors.append("Invalid risk parameters: values must be non-negative.")
            print("Risk Config ............ FAIL (Negative values detected)")
        else:
            print(f"Risk Config ............ PASS (Max Cap: INR {max_total_cap:,.0f})")
    except ValueError as exc:
        errors.append(f"Invalid risk parameter format: {exc}")
        print("Risk Config ............ FAIL (Format error)")

    # 4. Polling & Logging
    try:
        order_poll = int(os.getenv("ORDER_POLL_INTERVAL_SECONDS", "8"))
        price_poll = int(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "5"))
        print(f"Polling Config ......... PASS (Price: {price_poll}s, Order: {order_poll}s)")
    except ValueError:
        errors.append("Polling intervals must be integers.")
        print("Polling Config ......... FAIL")

    log_dir = os.getenv("LOG_DIR", "logs").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip()
    print(f"Log Config ............. PASS (Level: {log_level}, Dir: {log_dir})")

    # 5. Optional Subsystems
    gdrive_enabled = os.getenv("GDRIVE_BACKUP_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    if gdrive_enabled:
        svc_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
        folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()
        if not svc_json or not folder_id:
            errors.append("GDRIVE_BACKUP_ENABLED=true requires GDRIVE_SERVICE_ACCOUNT_JSON and GDRIVE_FOLDER_ID.")
            print("Backup Subsystem ....... FAIL (Missing credentials)")
        else:
            print("Backup Subsystem ....... PASS (Enabled)")
    else:
        print("Backup Subsystem ....... PASS (Disabled)")

    webhook_enabled = os.getenv("WEBHOOK_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    if webhook_enabled:
        secret = os.getenv("WEBHOOK_SECRET", "").strip()
        if not secret:
            errors.append("WEBHOOK_ENABLED=true requires WEBHOOK_SECRET.")
            print("Webhook Subsystem ...... FAIL (Missing secret)")
        else:
            print("Webhook Subsystem ...... PASS (Enabled)")
    else:
        print("Webhook Subsystem ...... PASS (Disabled)")

    print("\n=========================================")
    if errors:
        print("RESULT: FAIL")
        print("=========================================\n")
        print("Errors:")
        for err in errors:
            print(f" - {err}")
        return False

    print("RESULT: PASS")
    print("=========================================\n")
    return True


if __name__ == "__main__":
    success = run_preflight()
    sys.exit(0 if success else 1)
