"""Technical Indicator Calculation Engine for Indian Equities.

Computes EMA 20/50/200, RSI 14, MACD (12,26,9), ATR 14, ADX 14, VWAP,
Volume SMA 20, Bollinger Bands (20,2), and Candlestick Price Action metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from engine.data.base import OHLCVCandle


@dataclass
class IndicatorSnapshot:
    """Consolidated technical snapshot calculated from OHLCV series."""
    symbol: str
    timeframe: str
    last_price: float
    open: float | None = None

    # Moving Averages
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None

    # Momentum
    rsi: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None

    # Trend Strength & Volatility
    adx: float | None = None
    di_plus: float | None = None
    di_minus: float | None = None
    atr: float | None = None
    atr_pct: float | None = None

    # Bollinger Bands
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_bandwidth: float | None = None
    bb_pct_b: float | None = None

    # Volume & VWAP
    vwap: float | None = None
    volume_sma_20: float | None = None
    volume_surge_ratio: float = 1.0

    # Key Levels & Volatility Squeeze
    resistance_20: float | None = None
    support_20: float | None = None
    is_nr7: bool = False

    @property
    def is_ema_aligned_bullish(self) -> bool:
        """Returns True if Price > EMA20 > EMA50 > EMA200 (or EMA20 > EMA50)."""
        if self.ema_20 and self.ema_50 and self.ema_200:
            return self.last_price >= self.ema_20 >= self.ema_50 >= self.ema_200
        if self.ema_20 and self.ema_50:
            return self.last_price >= self.ema_20 >= self.ema_50
        return False

    @property
    def is_rsi_bullish(self) -> bool:
        """RSI in bullish momentum zone (55 - 75)."""
        return self.rsi is not None and 55.0 <= self.rsi <= 75.0

    @property
    def is_adx_trending(self) -> bool:
        """ADX > 20 and DI+ > DI-."""
        if self.adx is not None and self.di_plus is not None and self.di_minus is not None:
            return self.adx >= 20.0 and self.di_plus > self.di_minus
        return False

    @property
    def is_volume_confirmed(self) -> bool:
        """Current volume is at least 1.3x 20-period average volume."""
        return self.volume_surge_ratio >= 1.3

    @property
    def is_above_vwap(self) -> bool:
        """Price is trading above Volume Weighted Average Price."""
        if self.vwap is not None and self.vwap > 0:
            return self.last_price >= self.vwap
        return True


class TechnicalIndicatorEngine:
    """Calculates full suite of technical indicators from raw OHLCV bars."""

    @staticmethod
    def calculate_ema(values: list[float], period: int) -> list[float]:
        """Calculates Exponential Moving Average series."""
        if len(values) < period or period <= 0:
            return [float("nan")] * len(values)

        ema = [float("nan")] * len(values)
        # Seed first EMA with SMA
        sma = sum(values[:period]) / period
        ema[period - 1] = sma
        multiplier = 2.0 / (period + 1)

        for i in range(period, len(values)):
            ema[i] = (values[i] - ema[i - 1]) * multiplier + ema[i - 1]

        return ema

    @staticmethod
    def calculate_rsi(closes: list[float], period: int = 14) -> list[float]:
        """Calculates Relative Strength Index (RSI)."""
        if len(closes) < period + 1:
            return [float("nan")] * len(closes)

        rsi = [float("nan")] * len(closes)
        gains = []
        losses = []

        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))

        if len(gains) < period:
            return rsi

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                rsi[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    @classmethod
    def calculate_macd(
        cls,
        closes: list[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> tuple[list[float], list[float], list[float]]:
        """Calculates MACD line, signal line, and histogram."""
        if len(closes) < slow_period:
            nan_arr = [float("nan")] * len(closes)
            return nan_arr, nan_arr, nan_arr

        fast_ema = cls.calculate_ema(closes, fast_period)
        slow_ema = cls.calculate_ema(closes, slow_period)

        macd_line = []
        for f, s in zip(fast_ema, slow_ema):
            if math.isnan(f) or math.isnan(s):
                macd_line.append(float("nan"))
            else:
                macd_line.append(f - s)

        # Signal line is EMA of MACD line (filtering valid values)
        valid_macd_indices = [i for i, val in enumerate(macd_line) if not math.isnan(val)]
        signal_line = [float("nan")] * len(closes)
        histogram = [float("nan")] * len(closes)

        if len(valid_macd_indices) >= signal_period:
            valid_macd = [macd_line[i] for i in valid_macd_indices]
            valid_signal = cls.calculate_ema(valid_macd, signal_period)

            for idx, orig_i in enumerate(valid_macd_indices):
                sig_val = valid_signal[idx]
                signal_line[orig_i] = sig_val
                if not math.isnan(sig_val):
                    histogram[orig_i] = macd_line[orig_i] - sig_val

        return macd_line, signal_line, histogram

    @staticmethod
    def calculate_atr(candles: list[OHLCVCandle], period: int = 14) -> list[float]:
        """Calculates Average True Range (ATR)."""
        if len(candles) < period + 1:
            return [float("nan")] * len(candles)

        tr = [candles[0].high - candles[0].low]
        for i in range(1, len(candles)):
            h = candles[i].high
            l = candles[i].low
            prev_c = candles[i - 1].close
            tr.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))

        atr = [float("nan")] * len(candles)
        atr[period - 1] = sum(tr[:period]) / period

        for i in range(period, len(candles)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        return atr

    @staticmethod
    def calculate_adx(candles: list[OHLCVCandle], period: int = 14) -> tuple[list[float], list[float], list[float]]:
        """Calculates Average Directional Index (ADX), DI+, and DI-."""
        n = len(candles)
        nan_arr = [float("nan")] * n
        if n < period * 2:
            return nan_arr, nan_arr, nan_arr

        tr_list = [0.0]
        plus_dm = [0.0]
        minus_dm = [0.0]

        for i in range(1, n):
            h, l, prev_c = candles[i].high, candles[i].low, candles[i - 1].close
            prev_h, prev_l = candles[i - 1].high, candles[i - 1].low

            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            up_move = h - prev_h
            down_move = prev_l - l

            p_dm = up_move if up_move > down_move and up_move > 0 else 0.0
            m_dm = down_move if down_move > up_move and down_move > 0 else 0.0

            tr_list.append(tr)
            plus_dm.append(p_dm)
            minus_dm.append(m_dm)

        # Smoothed TR, +DM, -DM
        smoothed_tr = sum(tr_list[1 : period + 1])
        smoothed_pdm = sum(plus_dm[1 : period + 1])
        smoothed_mdm = sum(minus_dm[1 : period + 1])

        di_plus = [float("nan")] * n
        di_minus = [float("nan")] * n
        dx = [float("nan")] * n

        if smoothed_tr > 0:
            di_plus[period] = (smoothed_pdm / smoothed_tr) * 100.0
            di_minus[period] = (smoothed_mdm / smoothed_tr) * 100.0
            diff = abs(di_plus[period] - di_minus[period])
            total = di_plus[period] + di_minus[period]
            dx[period] = (diff / total * 100.0) if total > 0 else 0.0

        for i in range(period + 1, n):
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr_list[i]
            smoothed_pdm = smoothed_pdm - (smoothed_pdm / period) + plus_dm[i]
            smoothed_mdm = smoothed_mdm - (smoothed_mdm / period) + minus_dm[i]

            if smoothed_tr > 0:
                p_di = (smoothed_pdm / smoothed_tr) * 100.0
                m_di = (smoothed_mdm / smoothed_tr) * 100.0
                di_plus[i] = p_di
                di_minus[i] = m_di
                diff = abs(p_di - m_di)
                total = p_di + m_di
                dx[i] = (diff / total * 100.0) if total > 0 else 0.0

        adx = [float("nan")] * n
        valid_dx = [d for d in dx[period:] if not math.isnan(d)]
        if len(valid_dx) >= period:
            adx_start_idx = period + period - 1
            if adx_start_idx < n:
                adx[adx_start_idx] = sum(dx[period : period + period]) / period
                for i in range(adx_start_idx + 1, n):
                    if not math.isnan(dx[i]):
                        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return adx, di_plus, di_minus

    @staticmethod
    def calculate_bollinger_bands(
        closes: list[float], period: int = 20, std_dev: float = 2.0
    ) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
        """Calculates Bollinger Bands: Upper, Middle, Lower, Bandwidth, %B."""
        n = len(closes)
        nan_arr = [float("nan")] * n
        if n < period:
            return nan_arr, nan_arr, nan_arr, nan_arr, nan_arr

        upper = [float("nan")] * n
        middle = [float("nan")] * n
        lower = [float("nan")] * n
        bandwidth = [float("nan")] * n
        pct_b = [float("nan")] * n

        for i in range(period - 1, n):
            window = closes[i - period + 1 : i + 1]
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / period
            sd = math.sqrt(variance)

            up = mean + (sd * std_dev)
            lo = mean - (sd * std_dev)

            upper[i] = up
            middle[i] = mean
            lower[i] = lo
            bandwidth[i] = ((up - lo) / mean * 100.0) if mean > 0 else 0.0
            pct_b[i] = ((closes[i] - lo) / (up - lo)) if (up - lo) > 0 else 0.5

        return upper, middle, lower, bandwidth, pct_b

    @staticmethod
    def calculate_vwap(candles: list[OHLCVCandle]) -> float | None:
        """Calculates Volume Weighted Average Price across the candle series."""
        total_vol = 0.0
        cum_pv = 0.0
        for c in candles:
            typical_price = (c.high + c.low + c.close) / 3.0
            cum_pv += typical_price * c.volume
            total_vol += c.volume

        return (cum_pv / total_vol) if total_vol > 0 else None

    @classmethod
    def compute_snapshot(
        cls,
        symbol: str,
        candles: list[OHLCVCandle],
        timeframe: str = "1d",
    ) -> IndicatorSnapshot:
        """Generates comprehensive IndicatorSnapshot from OHLCV series."""
        if not candles:
            return IndicatorSnapshot(symbol=symbol, timeframe=timeframe, last_price=0.0)

        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        last_price = closes[-1]

        # EMAs
        ema_20 = cls.calculate_ema(closes, 20)[-1]
        ema_50 = cls.calculate_ema(closes, 50)[-1]
        ema_200 = cls.calculate_ema(closes, 200)[-1]

        # RSI
        rsi_vals = cls.calculate_rsi(closes, 14)
        rsi = rsi_vals[-1] if not math.isnan(rsi_vals[-1]) else None

        # MACD
        m_line, s_line, h_line = cls.calculate_macd(closes, 12, 26, 9)
        macd_line = m_line[-1] if not math.isnan(m_line[-1]) else None
        macd_signal = s_line[-1] if not math.isnan(s_line[-1]) else None
        macd_hist = h_line[-1] if not math.isnan(h_line[-1]) else None

        # ATR
        atr_vals = cls.calculate_atr(candles, 14)
        atr = atr_vals[-1] if not math.isnan(atr_vals[-1]) else None
        atr_pct = (atr / last_price * 100.0) if atr and last_price > 0 else None

        # ADX & DIs
        adx_vals, di_p_vals, di_m_vals = cls.calculate_adx(candles, 14)
        adx = adx_vals[-1] if not math.isnan(adx_vals[-1]) else None
        di_plus = di_p_vals[-1] if not math.isnan(di_p_vals[-1]) else None
        di_minus = di_m_vals[-1] if not math.isnan(di_m_vals[-1]) else None

        # Bollinger Bands
        bb_u, bb_m, bb_l, bb_bw, bb_pb = cls.calculate_bollinger_bands(closes, 20, 2.0)
        bb_upper = bb_u[-1] if not math.isnan(bb_u[-1]) else None
        bb_middle = bb_m[-1] if not math.isnan(bb_m[-1]) else None
        bb_lower = bb_l[-1] if not math.isnan(bb_l[-1]) else None
        bb_bandwidth = bb_bw[-1] if not math.isnan(bb_bw[-1]) else None
        bb_pct_b = bb_pb[-1] if not math.isnan(bb_pb[-1]) else None

        # Volume & VWAP
        vwap = cls.calculate_vwap(candles)
        recent_vols = volumes[-20:]
        vol_sma_20 = sum(recent_vols) / len(recent_vols) if recent_vols else volumes[-1]
        surge_ratio = (volumes[-1] / vol_sma_20) if vol_sma_20 > 0 else 1.0

        # Key Levels (20-period swing high/low)
        lookback = min(20, len(highs))
        resistance_20 = max(highs[-lookback:]) if lookback > 0 else last_price
        support_20 = min(lows[-lookback:]) if lookback > 0 else last_price

        # Genuine NR7 Calculation (Narrowest High-Low Range of the last 7 bars)
        is_nr7 = False
        if len(candles) >= 7:
            ranges = [(candles[idx].high - candles[idx].low) for idx in range(-7, 0)]
            today_range = ranges[-1]
            prior_6_ranges = ranges[:-1]
            if prior_6_ranges and today_range < min(prior_6_ranges) and today_range > 0:
                is_nr7 = True

        return IndicatorSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            last_price=last_price,
            open=candles[-1].open if candles else last_price,
            ema_20=ema_20 if not math.isnan(ema_20) else None,
            ema_50=ema_50 if not math.isnan(ema_50) else None,
            ema_200=ema_200 if not math.isnan(ema_200) else None,
            rsi=rsi,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
            adx=adx,
            di_plus=di_plus,
            di_minus=di_minus,
            atr=atr,
            atr_pct=atr_pct,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_bandwidth=bb_bandwidth,
            bb_pct_b=bb_pct_b,
            vwap=vwap,
            volume_sma_20=vol_sma_20,
            volume_surge_ratio=surge_ratio,
            resistance_20=resistance_20,
            support_20=support_20,
            is_nr7=is_nr7,
        )
