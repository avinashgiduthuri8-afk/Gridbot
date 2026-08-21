"""Tests for Sector Strength & Relative Momentum Matrix."""

from engine.data.base import SectorQuote
from engine.sectors.sector_analyzer import SectorStrengthAnalyzer


def test_sector_matrix_ranking():
    analyzer = SectorStrengthAnalyzer()
    sector_quotes = {
        "IT": SectorQuote(sector="IT", index_symbol="^CNXIT", change_pct_1d=2.1, relative_strength=1.5, status="LEADING"),
        "Banking": SectorQuote(sector="Banking", index_symbol="^NSEBANK", change_pct_1d=0.8, relative_strength=0.2, status="IMPROVING"),
        "Auto": SectorQuote(sector="Auto", index_symbol="^CNXAUTO", change_pct_1d=-1.2, relative_strength=-1.8, status="LAGGING"),
    }
    matrix = analyzer.evaluate_sectors(sector_quotes)

    assert "IT" in matrix.leading_sectors
    assert "Banking" in matrix.improving_sectors
    assert "Auto" in matrix.lagging_sectors

    score, name, rank, status = analyzer.evaluate_stock_sector("TCS", matrix)
    assert name == "IT"
    assert score == 5.0  # Leading sector gets 5.0 pts
    assert rank == 1

    score_auto, name_auto, rank_auto, status_auto = analyzer.evaluate_stock_sector("MARUTI", matrix)
    assert name_auto == "Auto"
    assert score_auto == 1.0  # Lagging sector gets 1.0 pts
