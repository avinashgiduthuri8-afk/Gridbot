"""News Sentiment & Corporate Event Evaluator for Indian Equities.

Evaluates earnings announcements, quarterly results, corporate filings,
and headline sentiment to modify signal confidence and filter event risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.data.base import NewsItem
from utils.logger import get_logger

log = get_logger("news_evaluator")


@dataclass
class SentimentAnalysis:
    symbol: str
    sentiment: str = "NEUTRAL"       # POSITIVE, NEUTRAL, NEGATIVE
    score: float = 3.5              # 0.0 to 5.0 pts in signal scoring
    has_earnings_risk: bool = False  # True if results scheduled today/tomorrow
    is_vetoed: bool = False          # True if severe negative news prevents trade
    reason: str = "No material adverse news"
    recent_headlines: list[str] = field(default_factory=list)


class NewsSentimentEvaluator:
    """Evaluates news items and corporate event calendars for a stock candidate."""

    def evaluate_news(self, symbol: str, news_items: list[NewsItem]) -> SentimentAnalysis:
        """Evaluates news sentiment and event risk."""
        if not news_items:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="NEUTRAL",
                score=0.0,
                reason="Quiet news flow / No recent corporate events",
            )

        headlines = [n.title for n in news_items]
        pos_count = 0
        neg_count = 0
        earnings_event = False
        severe_negative = False

        for n in news_items:
            if n.is_earnings_event:
                earnings_event = True
            if n.sentiment == "POSITIVE" or n.impact_score > 0.3:
                pos_count += 1
            elif n.sentiment == "NEGATIVE" or n.impact_score < -0.3:
                neg_count += 1
                if n.impact_score <= -0.7 or "fraud" in n.title.lower() or "raid" in n.title.lower() or "default" in n.title.lower():
                    severe_negative = True

        if severe_negative:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="NEGATIVE",
                score=0.0,
                is_vetoed=True,
                reason="Severe negative corporate/regulatory event detected",
                recent_headlines=headlines[:3],
            )

        if earnings_event:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="NEUTRAL",
                score=2.0,
                has_earnings_risk=True,
                reason="Earnings / Result announcement window active",
                recent_headlines=headlines[:3],
            )

        if pos_count > neg_count and pos_count >= 1:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="POSITIVE",
                score=5.0,
                reason=f"Positive corporate developments ({pos_count} positive items)",
                recent_headlines=headlines[:3],
            )
        elif neg_count > pos_count:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="NEGATIVE",
                score=1.5,
                reason=f"Negative news sentiment ({neg_count} negative items)",
                recent_headlines=headlines[:3],
            )

        return SentimentAnalysis(
            symbol=symbol,
            sentiment="NEUTRAL",
            score=3.5,
            reason="Neutral news flow",
            recent_headlines=headlines[:3],
        )
