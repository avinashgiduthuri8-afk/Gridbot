---
name: Log channels
description: Valid log channel names enforced at runtime by get_logger().
---

## Rule
`utils/logger.py` enforces a fixed set of channel names. Using any other name raises `ValueError` at import time.

Valid channels: `trading`, `exchange`, `telegram`, `database`, `grid`, `errors`

**Why:** The logger creates one file per channel. The set is hardcoded in `LOG_CHANNELS` in `utils/logger.py` line ~18.

**How to apply:** New modules in `trading/` should use `get_logger("trading")`. Exchange modules use `get_logger("exchange")`. Do not invent new channel names without adding them to `LOG_CHANNELS`.
