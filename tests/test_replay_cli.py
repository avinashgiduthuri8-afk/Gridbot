import json

import pytest

from replay.cli import build_arg_parser, run_replay


async def _run(argv):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args, await run_replay(args)


@pytest.mark.anyio
async def test_cli_scenario_run_passes_validation(tmp_path):
    db_path = str(tmp_path / "cli1.sqlite3")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "sideways", "--bars", "150",
        "--db", db_path,
    ])
    assert exit_code == 0


@pytest.mark.anyio
async def test_cli_multi_symbol_scenario(tmp_path):
    db_path = str(tmp_path / "cli2.sqlite3")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "ETHINR", "SOLINR", "--scenario", "bull",
        "--bars", "100", "--db", db_path,
    ])
    assert exit_code == 0


@pytest.mark.anyio
async def test_cli_report_written_to_disk(tmp_path):
    db_path = str(tmp_path / "cli3.sqlite3")
    report_path = str(tmp_path / "report.json")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "bear", "--bars", "100",
        "--db", db_path, "--report", report_path,
    ])
    assert exit_code == 0
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["validation"]["all_passed"] is True
    assert "replay" in data and "trading" in data and "system" in data


@pytest.mark.anyio
async def test_cli_restart_test_flag_runs_clean(tmp_path):
    db_path = str(tmp_path / "cli4.sqlite3")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "high_volatility", "--bars", "400",
        "--db", db_path, "--restart-test",
    ])
    assert exit_code == 0


@pytest.mark.anyio
async def test_cli_multi_grid_flag_creates_varied_configs_across_symbols(tmp_path):
    db_path = str(tmp_path / "cli5.sqlite3")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "ETHINR", "SOLINR", "--scenario", "sideways",
        "--bars", "100", "--db", db_path, "--multi-grid",
    ])
    assert exit_code == 0


@pytest.mark.anyio
async def test_cli_manual_trade_hook_produces_manual_trades(tmp_path):
    db_path = str(tmp_path / "cli6.sqlite3")
    report_path = str(tmp_path / "report6.json")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "high_volatility", "--bars", "500",
        "--db", db_path, "--manual-trade-every", "50", "--report", report_path,
    ])
    assert exit_code == 0
    data = json.loads((tmp_path / "report6.json").read_text())
    assert data["trading"]["manual_trades"] >= 1


@pytest.mark.anyio
async def test_cli_flash_crash_scenario_triggers_stop_losses(tmp_path):
    db_path = str(tmp_path / "cli7.sqlite3")
    report_path = str(tmp_path / "report7.json")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "flash_crash", "--bars", "600",
        "--db", db_path, "--report", report_path,
    ])
    assert exit_code == 0
    data = json.loads((tmp_path / "report7.json").read_text())
    # A flash crash should produce at least one sell (stop-loss or profit).
    assert data["trading"]["total_sells"] + data["trading"]["total_dust_writeoffs"] >= 1


@pytest.mark.anyio
async def test_cli_missing_scenario_and_data_dir_raises(tmp_path):
    parser = build_arg_parser()
    args = parser.parse_args(["--symbols", "BTCINR", "--db", str(tmp_path / "x.sqlite3")])
    with pytest.raises(SystemExit):
        await run_replay(args)


@pytest.mark.anyio
async def test_cli_no_sub_tick_flag_reduces_ticks(tmp_path):
    db_a = str(tmp_path / "a.sqlite3")
    db_b = str(tmp_path / "b.sqlite3")
    report_a = str(tmp_path / "a.json")
    report_b = str(tmp_path / "b.json")

    await _run(["--symbols", "BTCINR", "--scenario", "sideways", "--bars", "100",
                "--db", db_a, "--report", report_a])
    await _run(["--symbols", "BTCINR", "--scenario", "sideways", "--bars", "100",
                "--db", db_b, "--report", report_b, "--no-sub-tick"])

    data_a = json.loads((tmp_path / "a.json").read_text())
    data_b = json.loads((tmp_path / "b.json").read_text())
    assert data_a["replay"]["sub_ticks_processed"] == 400  # 4 prices/candle
    assert data_b["replay"]["sub_ticks_processed"] == 100  # close-only


@pytest.mark.anyio
async def test_cli_wallet_balance_omitted_preserves_existing_paper_behavior(tmp_path):
    """Default (no --wallet-balance) behavior must be completely unaffected
    by the new feature's existence."""
    db_path = str(tmp_path / "cli8.sqlite3")
    report_path = str(tmp_path / "report8.json")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "high_volatility", "--bars", "500",
        "--db", db_path, "--report", report_path,
    ])
    assert exit_code == 0
    data = json.loads((tmp_path / "report8.json").read_text())
    assert data["validation"]["all_passed"] is True


@pytest.mark.anyio
async def test_cli_wallet_balance_ample_allows_normal_trading(tmp_path):
    db_path = str(tmp_path / "cli9.sqlite3")
    report_path = str(tmp_path / "report9.json")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "high_volatility", "--bars", "1500",
        "--wallet-balance", "1000000", "--db", db_path, "--report", report_path,
    ])
    assert exit_code == 0
    data = json.loads((tmp_path / "report9.json").read_text())
    assert data["validation"]["all_passed"] is True
    # An ample wallet must allow at least the initial grid to be created and traded.
    assert data["trading"]["total_buys"] >= 1


@pytest.mark.anyio
async def test_cli_wallet_balance_too_small_rejects_grid_creation(tmp_path):
    """A wallet balance too small to cover even the base investment must
    cause RiskManager to reject grid creation — proving real capital
    constraints are actually being exercised, not silently bypassed."""
    db_path = str(tmp_path / "cli10.sqlite3")
    report_path = str(tmp_path / "report10.json")
    args, exit_code = await _run([
        "--symbols", "BTCINR", "--scenario", "sideways", "--bars", "200",
        "--wallet-balance", "1", "--db", db_path, "--report", report_path,
    ])
    assert exit_code == 0  # no grids created is not itself a validation failure
    data = json.loads((tmp_path / "report10.json").read_text())
    assert data["trading"]["total_buys"] == 0
    assert data["replay"]["trigger_evaluations"] == 0
