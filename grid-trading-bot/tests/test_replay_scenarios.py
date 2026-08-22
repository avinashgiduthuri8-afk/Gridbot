import pytest

from replay.scenarios import SCENARIO_NAMES, generate_multi_symbol_scenario, generate_scenario


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_generate_scenario_produces_requested_bar_count(name):
    candles = generate_scenario(name, "BTCINR", bars=100, seed=1)
    assert len(candles) == 100


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_generate_scenario_prices_stay_positive_and_ordered(name):
    candles = generate_scenario(name, "BTCINR", bars=200, seed=2)
    for c in candles:
        assert c.close > 0
        assert c.high >= max(c.open, c.close)
        assert c.low <= min(c.open, c.close)


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_generate_scenario_respects_price_precision(name):
    candles = generate_scenario(name, "BTCINR", bars=200, seed=3, price_precision=2)
    for c in candles:
        assert round(c.open, 2) == c.open
        assert round(c.close, 2) == c.close
        assert round(c.high, 2) == c.high
        assert round(c.low, 2) == c.low


def test_generate_scenario_is_deterministic_given_seed():
    a = generate_scenario("bull", "BTCINR", bars=50, seed=7)
    b = generate_scenario("bull", "BTCINR", bars=50, seed=7)
    assert [c.close for c in a] == [c.close for c in b]


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        generate_scenario("moon_mission", "BTCINR", bars=10)


def test_bull_trends_upward_on_average():
    candles = generate_scenario("bull", "BTCINR", bars=500, seed=5)
    assert candles[-1].close > candles[0].close


def test_bear_trends_downward_on_average():
    candles = generate_scenario("bear", "BTCINR", bars=500, seed=5)
    assert candles[-1].close < candles[0].close


def test_flash_crash_has_a_deep_drop_and_partial_recovery():
    candles = generate_scenario("flash_crash", "BTCINR", start_price=100.0, bars=300, seed=9)
    min_price = min(c.low for c in candles)
    assert min_price < 100.0 * 0.5  # a genuine crash, not just noise
    # some recovery happens after the trough
    trough_index = min(range(len(candles)), key=lambda i: candles[i].low)
    assert candles[-1].close > min_price


def test_gap_up_has_one_large_jump():
    candles = generate_scenario("gap_up", "BTCINR", start_price=100.0, bars=100, seed=11)
    biggest_jump = max(c.close / c.open for c in candles)
    assert biggest_jump > 1.03


def test_gap_down_has_one_large_drop():
    candles = generate_scenario("gap_down", "BTCINR", start_price=100.0, bars=100, seed=11)
    biggest_drop = min(c.close / c.open for c in candles)
    assert biggest_drop < 0.97


def test_high_volatility_has_wider_bars_than_low_volatility():
    hi = generate_scenario("high_volatility", "BTCINR", bars=200, seed=13)
    lo = generate_scenario("low_volatility", "BTCINR", bars=200, seed=13)
    hi_range = sum((c.high - c.low) / c.open for c in hi) / len(hi)
    lo_range = sum((c.high - c.low) / c.open for c in lo) / len(lo)
    assert hi_range > lo_range


def test_multi_symbol_scenario_produces_independent_paths():
    per_symbol = generate_multi_symbol_scenario("sideways", ["BTCINR", "ETHINR"], bars=100, seed=1)
    assert set(per_symbol.keys()) == {"BTCINR", "ETHINR"}
    btc_closes = [c.close for c in per_symbol["BTCINR"]]
    eth_closes = [c.close for c in per_symbol["ETHINR"]]
    assert btc_closes != eth_closes  # different seeded RNG streams, not lockstep
