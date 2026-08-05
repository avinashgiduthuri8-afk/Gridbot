"""Regression suite: shared validation is the only gatekeeper for every order path.

These tests verify exhaustively that:

  1. No order ever reaches OrderManager unless it has passed the shared validator.
  2. clamp_sell_quantity() output is always re-validated before reaching OrderManager.
  3. Every sell-side path handles violations by notifying / writing off rather than
     placing a bad order.
  4. Dust detection (qty < min_quantity) and min-notional breach are covered in both
     profit-sell and stop-loss paths.
  5. Paper-mode grids apply identical validation — the only difference is wallet balance.
  6. RecoveryManager never places new orders of its own.

MockExchange defaults (from conftest):
    ticker_price         = 54_000.0
    min_quantity         = 0.001
    min_amount (notional)= 10.0
    step_size            = 1e-5
    quantity_precision   = 5
    price_precision      = 2

Concrete scenarios:
  * base_investment=500 INR @ 54000 → qty≈0.00925, notional≈499.5   ✓ passes
  * base_investment=5 INR @ 54000   → qty≈0.00009 < 0.001            ✗ min_quantity
  * total_qty=0.0005 (dust)         → clamped=0.0005 < 0.001          ✗ min_quantity
  * total_qty=0.001, price=8001     → notional=8.001 < 10.0           ✗ min_notional
  * total_qty=0.001, price=7600     → notional=7.6   < 10.0           ✗ min_notional (SL)
"""

from __future__ import annotations

import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.base import MarketInfo
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.recovery import RecoveryManager
from utils.helpers import new_id, now_iso


# ---------------------------------------------------------------------------
# Module-level price constants
# ---------------------------------------------------------------------------

# price at which qty=0.001 produces notional just below min_amount=10.0
_LOW_PRICE: float = 8_001.0    # 0.001 * 8001 = 8.001 < 10.0
_LOW_AVG_ENTRY: float = 7_477.0  # ≈ 8001 / 1.07, so profit target ≈ _LOW_PRICE

# stop-loss price at which qty=0.001 is below min_notional
_SL_AVG_ENTRY: float = 8_000.0  # avg entry for stop-loss min-notional scenario
_SL_TRIGGER_PRICE: float = 7_600.0  # 8000 * (1 - 0.05) = 7600


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_grid(
    *,
    grid_id: str | None = None,
    symbol: str = "BTCINR",
    status: str = GridStatus.ACTIVE.value,
    mode: str = "real",
    current_level: int = 1,
    total_quantity: float = 0.00925,
    total_investment: float = 499.5,
    average_entry_price: float = 54_000.0,
    last_buy_price: float = 54_000.0,
    next_buy_price: float = 51_300.0,
    next_sell_price: float = 57_780.0,
    stop_loss_percentage: float = 50.0,
    dip_buy_amount: float = 100.0,
    profit_sell_amount: float = 150.0,
    profit_percentage: float = 7.0,
    max_levels: int = 10,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id or new_id("grd"),
        symbol=symbol,
        status=status,
        mode=mode,
        entry_price=average_entry_price,
        base_investment=500.0,
        dip_buy_amount=dip_buy_amount,
        dip_percentage=5.0,
        profit_sell_amount=profit_sell_amount,
        profit_percentage=profit_percentage,
        max_levels=max_levels,
        stop_loss_percentage=stop_loss_percentage,
        current_level=current_level,
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
        last_buy_price=last_buy_price,
        next_buy_price=next_buy_price,
        next_sell_price=next_sell_price,
        realized_profit=0.0,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


_BASE_START_PARAMS: dict = {
    "symbol": "BTCINR",
    "entry_price": 54_000.0,
    "base_investment": 500.0,
    "dip_buy_amount": 100.0,
    "dip_percentage": 5.0,
    "profit_sell_amount": 150.0,
    "profit_percentage": 7.0,
    "max_levels": 10,
    "stop_loss_percentage": 50.0,
}


@pytest.fixture
def order_manager(mock_exchange, repos):
    return OrderManager(mock_exchange, repos)


@pytest.fixture
def dca(mock_exchange, repos, order_manager, mock_notifier, permissive_risk_settings):
    return DCAManager(
        exchange=mock_exchange,
        repos=repos,
        order_manager=order_manager,
        notifier=mock_notifier,
        risk=RiskManager(permissive_risk_settings, repos),
    )


# ---------------------------------------------------------------------------
# 1.  Base buy validation
# ---------------------------------------------------------------------------

class TestBaseBuyValidation:
    """start_grid must call calculate_quantity_for_inr before placing any order."""

    @pytest.mark.anyio
    async def test_valid_amount_reaches_order_manager(self, dca, mock_exchange):
        """500 INR at 54000 → qty ≈ 0.00925, passes all rules, one buy order placed."""
        before = len(mock_exchange.orders_placed)
        await dca.start_grid(_BASE_START_PARAMS)
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "buy"

    @pytest.mark.anyio
    async def test_amount_below_min_quantity_raises_no_order(self, dca, mock_exchange):
        """5 INR at 54000 → qty ≈ 0.00009 < min_quantity 0.001.
        Validator raises ValueError; OrderManager must NOT be called."""
        before = len(mock_exchange.orders_placed)
        with pytest.raises(ValueError):
            await dca.start_grid({**_BASE_START_PARAMS, "base_investment": 5.0})
        assert len(mock_exchange.orders_placed) == before, (
            "OrderManager must not be reached when qty < min_quantity"
        )

    @pytest.mark.anyio
    async def test_amount_below_min_notional_raises_no_order(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """Qty >= min_quantity but notional < min_amount → ValueError, no order."""
        # Override market info: min_amount = 50, min_qty = 1, step = 1, price = 10
        # 30 INR → qty=3 ≥ min_qty=1, notional=30 < min_amount=50 → FAILS
        mock_exchange.market_info_override = MarketInfo(
            symbol="LOWCOIN",
            base_currency_precision=2,
            target_currency_precision=0,
            min_quantity=1.0,
            min_amount=50.0,
            step_size=1.0,
        )
        mock_exchange.ticker_price = 10.0
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        before = len(mock_exchange.orders_placed)
        with pytest.raises(ValueError):
            await dca.start_grid({
                **_BASE_START_PARAMS,
                "symbol": "LOWCOIN",
                "entry_price": 10.0,
                "base_investment": 30.0,  # notional=30 < min_amount=50
            })
        assert len(mock_exchange.orders_placed) == before


# ---------------------------------------------------------------------------
# 2.  Dip buy validation
# ---------------------------------------------------------------------------

class TestDipBuyValidation:
    """_execute_dip_buy must pass calculate_quantity_for_inr before placing any order."""

    @pytest.mark.anyio
    async def test_valid_dip_buy_reaches_order_manager(self, dca, repos, mock_exchange):
        """100 INR at 51000 → qty ≈ 0.00196, passes all rules, one buy order placed."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            next_buy_price=51_300.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=51_000.0)
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "buy"

    @pytest.mark.anyio
    async def test_dip_buy_amount_too_small_no_order_placed(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """1 INR at 51000 → qty ≈ 0.0000196 < min_quantity 0.001.
        ValueError is caught internally; no order reaches OrderManager."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            next_buy_price=51_300.0,
            dip_buy_amount=1.0,  # far too small
        )
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=51_000.0)
        assert len(mock_exchange.orders_placed) == before, (
            "DipBuy qty < min_quantity must not reach OrderManager"
        )

    @pytest.mark.anyio
    async def test_dip_buy_failure_leaves_grid_active(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """A failed dip buy validation does not change grid status — grid stays ACTIVE."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            next_buy_price=51_300.0,
            dip_buy_amount=1.0,
        )
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=51_000.0)
        updated = await repos.grids.get(grid.grid_id)
        assert updated["status"] == GridStatus.ACTIVE.value


# ---------------------------------------------------------------------------
# 3.  Profit sell validation
# ---------------------------------------------------------------------------

class TestProfitSellValidation:
    """_execute_profit_sell must validate after clamping; never forward a bad qty."""

    @pytest.mark.anyio
    async def test_valid_profit_sell_reaches_order_manager(self, dca, repos, mock_exchange):
        """Profit trigger at 58000 (next_sell=57780): normal sell order is placed."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            next_sell_price=57_780.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "sell"

    @pytest.mark.anyio
    async def test_valid_profit_sell_step_size_respected(self, dca, repos, mock_exchange):
        """The placed quantity must be an exact multiple of step_size=1e-5."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            next_sell_price=57_780.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)
        assert len(mock_exchange.orders_placed) >= 1
        qty = mock_exchange.orders_placed[-1].quantity
        step = 1e-5
        steps = round(qty / step)
        assert abs(qty - steps * step) < 1e-12, (
            f"qty {qty} is not a clean multiple of step_size {step}"
        )

    @pytest.mark.anyio
    async def test_profit_sell_clamped_below_min_quantity_no_order(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """total_qty=0.0005 < min_quantity=0.001 — dust position.
        After clamping, validate_quantity blocks the sell; dust_position_written_off is notified."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0005,  # dust
            total_investment=27.0,
            next_sell_price=57_780.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)
        assert len(mock_exchange.orders_placed) == before, (
            "Clamped dust qty must not reach OrderManager"
        )
        assert mock_notifier.was_called("dust_position_written_off"), (
            "User must be notified via dust_position_written_off when profit sell is blocked by dust"
        )

    @pytest.mark.anyio
    async def test_profit_sell_clamped_below_min_notional_no_order(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """total_qty=0.001 at price=8001: notional=8.001 < min_amount=10.0.
        validate_quantity blocks after clamp; dust_position_written_off is notified."""
        # desired_qty from 150 INR at 8002 ≈ 0.01874 → clamped to 0.001
        # validate_quantity(0.001, 8002, ...) → 0.001*8002=8.002 < 10.0 → FAILS
        grid = _make_grid(
            current_level=1,
            total_quantity=0.001,
            total_investment=_LOW_AVG_ENTRY * 0.001,
            average_entry_price=_LOW_AVG_ENTRY,
            next_sell_price=_LOW_PRICE,   # 8001
            profit_sell_amount=150.0,
        )
        mock_exchange.ticker_price = _LOW_PRICE
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        # Trigger at price just above next_sell_price
        await dca.check_grid_triggers(grid.grid_id, current_price=_LOW_PRICE + 1)
        assert len(mock_exchange.orders_placed) == before, (
            "Sub-minimum-notional qty must not reach OrderManager"
        )
        assert mock_notifier.was_called("dust_position_written_off")

    @pytest.mark.anyio
    async def test_profit_sell_desired_qty_exceeds_holding_clamped_correctly(
        self, dca, repos, mock_exchange
    ):
        """profit_sell_amount >> available holding: sell is clamped to total_quantity,
        not to the raw calculated amount. Clamped result must still pass validation."""
        # profit_sell_amount=999 → desired ≈ 0.01722 >> total_qty=0.01 → clamp to 0.01
        # 0.01 * 58000 = 580 > 10 → passes validation → order placed
        grid = _make_grid(
            current_level=2,
            total_quantity=0.01,
            total_investment=540.0,
            next_sell_price=57_780.0,
            profit_sell_amount=999.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)
        assert len(mock_exchange.orders_placed) == before + 1
        placed_qty = mock_exchange.orders_placed[-1].quantity
        assert placed_qty <= 0.01 + 1e-9, (
            "Placed qty must never exceed total_quantity after clamping"
        )


# ---------------------------------------------------------------------------
# 4.  Stop loss validation
# ---------------------------------------------------------------------------

class TestStopLossValidation:
    """_execute_stop_loss validates via validate_quantity; dust positions are written off."""

    @pytest.mark.anyio
    async def test_full_position_stop_loss_reaches_order_manager(
        self, dca, repos, mock_exchange
    ):
        """Normal position stop-loss at avg=54000, trigger at 26000 (50 % drop).
        Sell order must reach OrderManager."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "sell"

    @pytest.mark.anyio
    async def test_stop_loss_dust_position_no_order_placed(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """Dust position (0.0005 < min_quantity 0.001): stop-loss must NOT place any order.
        Position is written off as dust."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0005,  # dust
            total_investment=27.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert len(mock_exchange.orders_placed) == before, (
            "Stop-loss on dust position must not reach OrderManager"
        )

    @pytest.mark.anyio
    async def test_stop_loss_dust_grid_marked_stopped(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """After a dust write-off in stop-loss, grid status must be STOPPED."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0005,
            total_investment=27.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        updated = await repos.grids.get(grid.grid_id)
        assert updated["status"] == GridStatus.STOPPED.value

    @pytest.mark.anyio
    async def test_stop_loss_dust_error_notification_sent(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """Dust write-off in stop-loss must send a dust_position_written_off notification (not stop_loss_triggered)."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0005,
            total_investment=27.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert mock_notifier.was_called("dust_position_written_off"), (
            "Dust write-off must notify via dust_position_written_off channel"
        )
        assert not mock_notifier.was_called("stop_loss_triggered"), (
            "stop_loss_triggered must NOT be sent when no order was placed"
        )

    @pytest.mark.anyio
    async def test_stop_loss_dust_position_zeroes_holding(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """After dust write-off, total_quantity and total_investment are zeroed in DB."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0005,
            total_investment=27.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        updated = await repos.grids.get(grid.grid_id)
        assert updated["total_quantity"] == pytest.approx(0.0)
        assert updated["total_investment"] == pytest.approx(0.0)

    @pytest.mark.anyio
    async def test_stop_loss_min_notional_breach_no_order_placed(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """qty=0.001 but price=7600 → notional=7.6 < min_amount=10.0.
        Stop-loss validates this as dust → writes off, no order, STOPPED status."""
        # avg=8000, stop_loss_pct=5 → trigger at 8000*0.95=7600
        # validate_quantity(0.001, 7600, 0.001, min_notional=10.0) → 7.6 < 10.0 → FAILS
        grid = _make_grid(
            current_level=1,
            total_quantity=0.001,
            total_investment=8.0,
            average_entry_price=_SL_AVG_ENTRY,   # 8000
            stop_loss_percentage=5.0,             # trigger at 7600
        )
        mock_exchange.ticker_price = _SL_TRIGGER_PRICE
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=_SL_TRIGGER_PRICE)
        assert len(mock_exchange.orders_placed) == before, (
            "Min-notional breach in stop-loss must not reach OrderManager"
        )
        updated = await repos.grids.get(grid.grid_id)
        assert updated["status"] == GridStatus.STOPPED.value
        assert mock_notifier.was_called("dust_position_written_off")

    @pytest.mark.anyio
    async def test_stop_loss_success_notifies_stop_loss_triggered(
        self, dca, repos, mock_notifier
    ):
        """Successful stop-loss sell must send stop_loss_triggered notification."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            total_investment=499.5,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert mock_notifier.was_called("stop_loss_triggered")

    @pytest.mark.anyio
    async def test_stop_loss_success_zeroes_holding(self, dca, repos, mock_exchange):
        """After a successful stop-loss sell, total_quantity and total_investment are zeroed."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.00925,
            total_investment=499.5,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        updated = await repos.grids.get(grid.grid_id)
        assert updated["status"] == GridStatus.STOPPED.value
        assert updated["total_quantity"] == pytest.approx(0.0)
        assert updated["total_investment"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 5.  Clamp-below-minimum scenarios (explicit)
# ---------------------------------------------------------------------------

class TestClampedBelowMinimum:
    """Ensure the post-clamp revalidation catches every way a qty can become unsellable."""

    @pytest.mark.anyio
    async def test_profit_sell_clamped_to_dust_blocked_with_notification(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """profit_sell_amount forces a large desired_qty, clamped to dust 0.0003.
        validate_quantity blocks; dust_position_written_off notification sent."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0003,  # dust, will be clamped from any desired qty
            total_investment=16.2,
            next_sell_price=57_780.0,
            profit_sell_amount=999.0,  # pushes desired_qty >> total_qty
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)
        assert len(mock_exchange.orders_placed) == before
        assert mock_notifier.was_called("dust_position_written_off")

    @pytest.mark.anyio
    async def test_stop_loss_clamp_to_dust_write_off(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """total_qty=0.0003 (dust): stop-loss clamp keeps it at 0.0003 < 0.001.
        validate_quantity blocks; position written off; no order placed."""
        grid = _make_grid(
            current_level=1,
            total_quantity=0.0003,
            total_investment=16.2,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert len(mock_exchange.orders_placed) == before
        updated = await repos.grids.get(grid.grid_id)
        assert updated["status"] == GridStatus.STOPPED.value

    @pytest.mark.anyio
    async def test_profit_sell_clamp_to_min_notional_failure_blocked(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """profit_sell_amount forces a large desired_qty → clamped to total_qty=0.001.
        At price=8002: notional=8.002 < min_amount=10.0 → validate_quantity blocks."""
        # desired_qty for 999 INR at 8002 ≈ 0.1248 → clamped to 0.001
        # validate_quantity(0.001, 8002, 0.001, min_notional=10.0) → FAILS
        grid = _make_grid(
            current_level=1,
            total_quantity=0.001,
            total_investment=7.477,
            average_entry_price=_LOW_AVG_ENTRY,
            next_sell_price=_LOW_PRICE,   # 8001
            profit_sell_amount=999.0,
        )
        mock_exchange.ticker_price = _LOW_PRICE
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=_LOW_PRICE + 1)
        assert len(mock_exchange.orders_placed) == before
        assert mock_notifier.was_called("dust_position_written_off")


# ---------------------------------------------------------------------------
# 6.  Full position exit (multi-level hold)
# ---------------------------------------------------------------------------

class TestFullPositionExit:
    """Stop-loss on a multi-level position must sell exactly the full holding."""

    @pytest.mark.anyio
    async def test_multi_level_stop_loss_places_one_sell(self, dca, repos, mock_exchange):
        """2-level position: exactly one sell order placed."""
        grid = _make_grid(
            current_level=2,
            total_quantity=0.01850,
            total_investment=999.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        placed = mock_exchange.orders_placed[before:]
        assert len(placed) == 1
        assert placed[0].side == "sell"

    @pytest.mark.anyio
    async def test_multi_level_stop_loss_sell_qty_equals_total_qty(
        self, dca, repos, mock_exchange
    ):
        """Sell quantity must equal (step-floored) total_quantity, not a partial amount."""
        total_qty = 0.01850
        grid = _make_grid(
            current_level=2,
            total_quantity=total_qty,
            total_investment=999.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        placed_qty = mock_exchange.orders_placed[before].quantity
        # clamp_sell_quantity floors to the nearest step (1e-5), so placed_qty may be
        # up to one step below total_qty due to float arithmetic — that is correct.
        step = 1e-5
        assert placed_qty <= total_qty + 1e-9, "Must not exceed total holding"
        assert placed_qty >= total_qty - step - 1e-9, "Must not be more than one step below total"
        assert placed_qty > 0

    @pytest.mark.anyio
    async def test_multi_level_stop_loss_clears_holding_in_db(
        self, dca, repos, mock_exchange
    ):
        """After exit, DB must show total_quantity=0 and total_investment=0."""
        grid = _make_grid(
            current_level=2,
            total_quantity=0.01850,
            total_investment=999.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        updated = await repos.grids.get(grid.grid_id)
        assert updated["total_quantity"] == pytest.approx(0.0)
        assert updated["total_investment"] == pytest.approx(0.0)
        assert updated["status"] == GridStatus.STOPPED.value


# ---------------------------------------------------------------------------
# 7.  Paper mode: identical validation as real mode
# ---------------------------------------------------------------------------

class TestPaperModeValidationParity:
    """Paper mode differs only in wallet balance — validation rules are identical.
    OrderManager.place_dca_order accepts mode='paper' and logs accordingly;
    the underlying exchange mock tracks all orders the same way.
    """

    @pytest.mark.anyio
    async def test_paper_valid_base_buy_places_order(self, dca, mock_exchange):
        """Paper mode: 500 INR at 54000 → same validation path as real → order placed."""
        before = len(mock_exchange.orders_placed)
        await dca.start_grid({**_BASE_START_PARAMS, "mode": "paper"})
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "buy"

    @pytest.mark.anyio
    async def test_paper_amount_below_min_quantity_raises_no_order(
        self, dca, mock_exchange
    ):
        """Paper mode: 5 INR at 54000 → same ValueError as real mode; no order placed."""
        before = len(mock_exchange.orders_placed)
        with pytest.raises(ValueError):
            await dca.start_grid(
                {**_BASE_START_PARAMS, "mode": "paper", "base_investment": 5.0}
            )
        assert len(mock_exchange.orders_placed) == before

    @pytest.mark.anyio
    async def test_paper_dust_stop_loss_writes_off_no_order(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """Paper mode: dust stop-loss → same write-off as real mode; no order placed."""
        grid = _make_grid(
            mode="paper",
            current_level=1,
            total_quantity=0.0005,
            total_investment=27.0,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert len(mock_exchange.orders_placed) == before
        updated = await repos.grids.get(grid.grid_id)
        assert updated["status"] == GridStatus.STOPPED.value
        assert mock_notifier.was_called("dust_position_written_off")

    @pytest.mark.anyio
    async def test_paper_valid_stop_loss_places_sell(self, dca, repos, mock_exchange):
        """Paper mode: normal stop-loss → order placed exactly as in real mode."""
        grid = _make_grid(
            mode="paper",
            current_level=1,
            total_quantity=0.00925,
            total_investment=499.5,
            average_entry_price=54_000.0,
            stop_loss_percentage=50.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "sell"

    @pytest.mark.anyio
    async def test_paper_profit_sell_dust_notified(
        self, dca, repos, mock_exchange, mock_notifier
    ):
        """Paper mode: profit sell on dust position → order_failed notified, no order."""
        grid = _make_grid(
            mode="paper",
            current_level=1,
            total_quantity=0.0005,
            total_investment=27.0,
            next_sell_price=57_780.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)
        assert len(mock_exchange.orders_placed) == before
        assert mock_notifier.was_called("dust_position_written_off")

    @pytest.mark.anyio
    async def test_paper_valid_dip_buy_reaches_order_manager(
        self, dca, repos, mock_exchange
    ):
        """Paper mode: valid dip buy (100 INR at 51000) applies same validation as
        real mode and places a buy order."""
        grid = _make_grid(
            mode="paper",
            current_level=1,
            total_quantity=0.00925,
            next_buy_price=51_300.0,
            dip_buy_amount=100.0,
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=51_000.0)
        assert len(mock_exchange.orders_placed) == before + 1
        assert mock_exchange.orders_placed[-1].side == "buy"

    @pytest.mark.anyio
    async def test_paper_dip_buy_amount_too_small_no_order(
        self, mock_exchange, repos, mock_notifier, permissive_risk_settings
    ):
        """Paper mode: 1 INR dip buy → qty < min_quantity → ValueError caught internally;
        no order placed (identical to real mode)."""
        grid = _make_grid(
            mode="paper",
            current_level=1,
            total_quantity=0.00925,
            next_buy_price=51_300.0,
            dip_buy_amount=1.0,  # too small
        )
        dca = DCAManager(
            exchange=mock_exchange,
            repos=repos,
            order_manager=OrderManager(mock_exchange, repos),
            notifier=mock_notifier,
            risk=RiskManager(permissive_risk_settings, repos),
        )
        await repos.grids.create(grid)
        before = len(mock_exchange.orders_placed)
        await dca.check_grid_triggers(grid.grid_id, current_price=51_000.0)
        assert len(mock_exchange.orders_placed) == before, (
            "Paper dip buy qty < min_quantity must not reach OrderManager"
        )


# ---------------------------------------------------------------------------
# 8.  Recovery: never places new orders
# ---------------------------------------------------------------------------

class TestRecoveryDoesNotPlaceOrders:
    """RecoveryManager reconciles state; it must never call place_dca_order."""

    @pytest.fixture
    def recovery(self, mock_exchange, repos, mock_notifier, dca):
        return RecoveryManager(
            exchange=mock_exchange,
            repos=repos,
            notifier=mock_notifier,
            dca_manager=dca,
        )

    @pytest.mark.anyio
    async def test_offline_fill_reconciled_no_new_order(
        self, recovery, repos, mock_exchange
    ):
        """Recovery processes an offline fill via handle_order_filled.
        No new order must be placed — only state is updated."""
        from exchange.base import ExchangeOrder

        grid = _make_grid(current_level=1, total_quantity=0.00925)
        await repos.grids.create(grid)

        order = OrderRecord(
            order_id=new_id("ord"),
            grid_id=grid.grid_id,
            exchange_order_id="EX_RECOVERED_001",
            symbol="BTCINR",
            side="buy",
            order_type="market_order",
            price=54_000.0,
            quantity=0.001,
            filled_quantity=0.0,
            filled_price=0.0,
            status=OrderStatus.OPEN.value,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        await repos.orders.create(order)

        # Simulate the exchange showing this order as filled
        mock_exchange.status_overrides["EX_RECOVERED_001"] = ExchangeOrder(
            exchange_order_id="EX_RECOVERED_001",
            symbol="BTCINR",
            side="buy",
            price=54_000.0,
            quantity=0.001,
            filled_quantity=0.001,
            filled_price=54_000.0,
            status=OrderStatus.FILLED.value,
            raw_status="filled",
        )

        before = len(mock_exchange.orders_placed)
        summary = await recovery.recover()
        assert len(mock_exchange.orders_placed) == before, (
            "Recovery must not place any new orders"
        )
        assert summary["fills_recovered"] == 1

    @pytest.mark.anyio
    async def test_pending_no_exchange_id_marked_failed_no_new_order(
        self, recovery, repos, mock_exchange
    ):
        """PENDING order with no exchange_order_id → marked FAILED; no new order placed."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = OrderRecord(
            order_id=new_id("ord"),
            grid_id=grid.grid_id,
            exchange_order_id=None,
            symbol="BTCINR",
            side="buy",
            order_type="market_order",
            price=54_000.0,
            quantity=0.00925,
            filled_quantity=0.0,
            filled_price=0.0,
            status=OrderStatus.PENDING.value,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        await repos.orders.create(order)

        before = len(mock_exchange.orders_placed)
        await recovery.recover()
        assert len(mock_exchange.orders_placed) == before

        db_order = await repos.orders.get(order.order_id)
        assert db_order["status"] == OrderStatus.FAILED.value

    @pytest.mark.anyio
    async def test_recovery_with_multiple_grids_no_new_orders(
        self, recovery, repos, mock_exchange
    ):
        """Multiple grids with various order states: recovery touches none of them
        with new order placements."""
        from exchange.base import ExchangeOrder

        for i in range(3):
            grid = _make_grid(grid_id=f"grd_rcv_{i}", current_level=1, total_quantity=0.005)
            await repos.grids.create(grid)
            ex_id = f"EX_MULTI_{i}"
            order = OrderRecord(
                order_id=new_id("ord"),
                grid_id=grid.grid_id,
                exchange_order_id=ex_id,
                symbol="BTCINR",
                side="buy",
                order_type="market_order",
                price=54_000.0,
                quantity=0.005,
                filled_quantity=0.0,
                filled_price=0.0,
                status=OrderStatus.OPEN.value,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
            await repos.orders.create(order)
            mock_exchange.status_overrides[ex_id] = ExchangeOrder(
                exchange_order_id=ex_id,
                symbol="BTCINR",
                side="buy",
                price=54_000.0,
                quantity=0.005,
                filled_quantity=0.005,
                filled_price=54_000.0,
                status=OrderStatus.FILLED.value,
                raw_status="filled",
            )

        before = len(mock_exchange.orders_placed)
        summary = await recovery.recover()
        assert len(mock_exchange.orders_placed) == before, (
            "Recovery must not place new orders even with multiple grids"
        )
        assert summary["fills_recovered"] == 3
