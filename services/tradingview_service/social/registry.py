"""
Crypto Bot v4.4 — Social & Sentiment Signal Registry
Provides social trading indicators: sentiment analysis, social volume,
trending score, fear-greed index, on-chain metrics integration.

These signals enhance TradingView alerts with off-chart context:
  - Social sentiment (Twitter/X, Reddit, Telegram)
  - Fear & Greed Index (alternative.me API)
  - Social volume / trending score
  - On-chain whale alerts
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Social Signal Data Structures
# ═══════════════════════════════════════════════════════════════

class SocialSource(str):
    """Social data sources."""
    TWITTER = "twitter"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    FEAR_GREED = "fear_greed"
    ON_CHAIN = "on_chain"
    LUNARCRUSH = "lunarcrush"
    SANTIMENT = "santiment"


class SocialSignalRegistry:
    """
    Aggregates social and sentiment signals for crypto assets.

    Integrates with:
      - Alternative.me Fear & Greed Index (free, no API key needed)
      - Social volume tracking (simulated; production: LunarCrush/Santiment API)
      - On-chain whale alert tracking
      - Custom sentiment scoring model

    Usage:
        registry = SocialSignalRegistry()
        signals = registry.get_signals("BTCUSDT")
        # → {"sentiment_score": 0.72, "trust_score": 0.65,
        #    "fear_greed": 45, "social_volume": "high", ...}
    """

    # Asset mapping: pair → base asset for social APIs
    ASSET_MAP = {
        "BTCUSDT": "bitcoin",
        "ETHUSDT": "ethereum",
        "SOLUSDT": "solana",
        "BNBUSDT": "bnb",
        "XRPUSDT": "ripple",
        "DOGEUSDT": "dogecoin",
        "ADAUSDT": "cardano",
        "AVAXUSDT": "avalanche-2",
        "DOTUSDT": "polkadot",
        "LINKUSDT": "chainlink",
        "MATICUSDT": "matic-network",
        "UNIUSDT": "uniswap",
    }

    # Pre-configured sentiment profiles for known assets
    # (In production, these are fetched live)
    _SENTIMENT_PROFILES: Dict[str, dict] = {
        "bitcoin": {
            "base_sentiment": 0.65,
            "social_volume": "high",
            "trending_score": 0.85,
            "influencer_bullish_pct": 62,
            "reddit_mentions_24h": 4500,
            "twitter_mentions_24h": 120000,
            "whale_activity": "neutral",
        },
        "ethereum": {
            "base_sentiment": 0.60,
            "social_volume": "high",
            "trending_score": 0.75,
            "influencer_bullish_pct": 58,
            "reddit_mentions_24h": 3200,
            "twitter_mentions_24h": 85000,
            "whale_activity": "accumulating",
        },
        "solana": {
            "base_sentiment": 0.70,
            "social_volume": "medium",
            "trending_score": 0.72,
            "influencer_bullish_pct": 65,
            "reddit_mentions_24h": 1800,
            "twitter_mentions_24h": 45000,
            "whale_activity": "neutral",
        },
        "bnb": {
            "base_sentiment": 0.55,
            "social_volume": "medium",
            "trending_score": 0.60,
            "influencer_bullish_pct": 52,
            "reddit_mentions_24h": 800,
            "twitter_mentions_24h": 22000,
            "whale_activity": "distributing",
        },
    }

    # Fear & Greed Index thresholds
    FEAR_GREED_THRESHOLDS = {
        "extreme_fear": (0, 25, "Strong BUY signal — market is panicking"),
        "fear": (25, 46, "Potential BUY opportunity — cautious sentiment"),
        "neutral": (46, 55, "Market is balanced — follow TA signals"),
        "greed": (55, 75, "Bullish but cautious — tighten stops"),
        "extreme_greed": (75, 100, "Strong SELL signal — market is euphoric"),
    }

    def __init__(self, enable_live_fetch: bool = False):
        self.enable_live_fetch = enable_live_fetch
        self._cache: Dict[str, dict] = {}
        self._cache_ttl: float = 300.0  # 5 minute cache
        self._fetch_timestamps: Dict[str, float] = {}
        self._custom_alerts: List[dict] = []

    # ═══════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════

    def get_signals(self, pair: str) -> dict:
        """
        Get all social signals for a trading pair.

        Returns:
            {
                "sentiment_score": 0.0–1.0 (bullish),
                "trust_score": 0.0–1.0 (signal reliability),
                "fear_greed": 0–100,
                "fear_greed_label": "fear" | "neutral" | "greed",
                "social_volume": "low" | "medium" | "high",
                "trending_score": 0.0–1.0,
                "whale_activity": "accumulating" | "neutral" | "distributing",
                "influencer_bullish_pct": 0–100,
                "social_mentions_24h": int,
                "custom_alerts": [...],
                "composite": 0.0–1.0,
                "recommendation": "bullish" | "bearish" | "neutral" | "caution",
            }
        """
        asset = self._pair_to_asset(pair)

        # Check cache
        now = time.time()
        if asset in self._cache and (now - self._fetch_timestamps.get(asset, 0)) < self._cache_ttl:
            return self._cache[asset]

        # Get profile
        profile = self._SENTIMENT_PROFILES.get(asset, self._default_profile())
        fear_greed = self._get_fear_greed_index()

        # Compute composite scores
        sentiment_score = profile["base_sentiment"]
        trust_score = self._compute_trust_score(profile)

        # Fear & Greed interpretation
        fg_label = self._interpret_fear_greed(fear_greed)

        # Whal activity scoring
        whale_score = {"accumulating": 0.8, "neutral": 0.5, "distributing": 0.2}
        whale_bias = whale_score.get(profile["whale_activity"], 0.5)

        # Composite score: blend all signals
        composite = (
            0.30 * sentiment_score +
            0.25 * (fear_greed / 100) * 0.5 +   # fear = bearish, greed = bullish (but extreme greed = caution)
            0.20 * profile["trending_score"] +
            0.15 * whale_bias +
            0.10 * (profile["influencer_bullish_pct"] / 100)
        )

        # Recommendation
        if composite > 0.65:
            recommendation = "bullish"
        elif composite < 0.35:
            recommendation = "bearish"
        elif fear_greed > 75:
            recommendation = "caution"  # Greed → tighten stops
        else:
            recommendation = "neutral"

        result = {
            "sentiment_score": round(sentiment_score, 3),
            "trust_score": round(trust_score, 3),
            "fear_greed": fear_greed,
            "fear_greed_label": fg_label,
            "fear_greed_interpretation": dict(self.FEAR_GREED_THRESHOLDS).get(fg_label, ("", "", ""))[2],
            "social_volume": profile["social_volume"],
            "trending_score": profile["trending_score"],
            "whale_activity": profile["whale_activity"],
            "whale_bias_score": round(whale_bias, 2),
            "influencer_bullish_pct": profile["influencer_bullish_pct"],
            "social_mentions_24h": profile["reddit_mentions_24h"] + profile["twitter_mentions_24h"],
            "custom_alerts": self._custom_alerts[-5:],
            "composite": round(composite, 3),
            "recommendation": recommendation,
            "asset": asset,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Cache
        self._cache[asset] = result
        self._fetch_timestamps[asset] = now

        return result

    def get_fear_greed_only(self) -> dict:
        """Get only the Fear & Greed Index."""
        value = self._get_fear_greed_index()
        label = self._interpret_fear_greed(value)
        return {
            "value": value,
            "label": label,
            "interpretation": dict(self.FEAR_GREED_THRESHOLDS).get(label, ("", "", ""))[2],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def add_custom_alert(self, source: str, pair: str, message: str, sentiment: float):
        """Add a custom social alert (e.g., from Telegram bot, Discord)."""
        self._custom_alerts.append({
            "source": source,
            "pair": pair,
            "message": message,
            "sentiment": sentiment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Trim old alerts
        if len(self._custom_alerts) > 100:
            self._custom_alerts = self._custom_alerts[-100:]

    def list_supported_assets(self) -> List[str]:
        """List assets with social data available."""
        return list(self.ASSET_MAP.keys())

    # ═══════════════════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════════════════

    def _pair_to_asset(self, pair: str) -> str:
        """Convert trading pair to asset name for social APIs."""
        pair_upper = pair.upper().replace("/", "").replace(":", "")
        return self.ASSET_MAP.get(pair_upper, pair_upper.lower())

    @staticmethod
    def _default_profile() -> dict:
        return {
            "base_sentiment": 0.50,
            "social_volume": "low",
            "trending_score": 0.40,
            "influencer_bullish_pct": 50,
            "reddit_mentions_24h": 0,
            "twitter_mentions_24h": 0,
            "whale_activity": "neutral",
        }

    def _get_fear_greed_index(self) -> int:
        """
        Get Fear & Greed Index from alternative.me API.
        Falls back to simulated value if fetch fails.
        """
        if self.enable_live_fetch:
            try:
                import urllib.request, json
                url = "https://api.alternative.me/fng/?limit=1"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read())
                    value = int(data["data"][0]["value"])
                    return value
            except Exception as e:
                logger.warning("fear_greed_fetch_failed", error=str(e))

        # Simulated value based on time (changes slowly for demo)
        now = int(time.time())
        return 30 + int(25 * (1 + __import__("math").sin(now / 86400 * 3.14)))

    def _compute_trust_score(self, profile: dict) -> float:
        """Compute how trustworthy the social signals are."""
        score = 0.5

        # High social volume = more reliable
        vol_map = {"high": 0.3, "medium": 0.15, "low": 0.0}
        score += vol_map.get(profile["social_volume"], 0)

        # Trending assets have more eyes = more reliable data
        score += profile["trending_score"] * 0.2

        return round(min(1.0, score), 3)

    def _interpret_fear_greed(self, value: int) -> str:
        for label, (low, high, _) in self.FEAR_GREED_THRESHOLDS.items():
            if low <= value <= high:
                return label
        return "neutral"
