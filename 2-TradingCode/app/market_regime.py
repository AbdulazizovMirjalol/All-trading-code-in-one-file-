from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class MarketRegimeResult:
    regime: str
    trend_direction: str
    trend_strength: int
    volatility_state: str
    atr_percentile: float
    ema_slope_score: int
    adx_score: int
    structure_score: int
    reason: str


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _get_last_value(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    if df is None or df.empty or column not in df.columns:
        return default
    return _safe_float(df[column].iloc[-1], default)


def _calculate_atr_percentile(df: pd.DataFrame, atr_column: str = "ATR", lookback: int = 100) -> float:
    """
    Oxirgi ATR qiymati so'nggi lookback sham ichida nechanchi percentile ekanini hisoblaydi.
    0.80 degani ATR oxirgi davrga nisbatan yuqori volatility.
    """

    if df is None or df.empty or atr_column not in df.columns:
        return 0.0

    atr_series = df[atr_column].dropna().tail(lookback)

    if len(atr_series) < 20:
        return 0.0

    last_atr = atr_series.iloc[-1]

    if last_atr <= 0:
        return 0.0

    percentile = (atr_series <= last_atr).sum() / len(atr_series)

    return round(float(percentile), 2)


def _calculate_ema_slope_score(df: pd.DataFrame, ema_column: str = "EMA_50", lookback: int = 10) -> tuple[int, str]:
    """
    EMA slope orqali trend yo'nalishi va kuchini baholaydi.
    """

    if df is None or df.empty or ema_column not in df.columns:
        return 0, "UNKNOWN"

    ema = df[ema_column].dropna()

    if len(ema) < lookback + 2:
        return 0, "UNKNOWN"

    current = _safe_float(ema.iloc[-1])
    previous = _safe_float(ema.iloc[-lookback])

    if previous == 0:
        return 0, "UNKNOWN"

    slope_pct = ((current - previous) / previous) * 100

    abs_slope = abs(slope_pct)

    if abs_slope >= 0.25:
        score = 30
    elif abs_slope >= 0.15:
        score = 22
    elif abs_slope >= 0.08:
        score = 14
    elif abs_slope >= 0.03:
        score = 7
    else:
        score = 0

    if slope_pct > 0:
        direction = "UP"
    elif slope_pct < 0:
        direction = "DOWN"
    else:
        direction = "FLAT"

    return score, direction


def _calculate_adx_score(df: pd.DataFrame, adx_column: str = "ADX") -> int:
    """
    ADX trend kuchini bildiradi.
    ADX yo'nalishni emas, faqat trend kuchini bildiradi.
    """

    adx = _get_last_value(df, adx_column, 0.0)

    if adx >= 35:
        return 30
    if adx >= 28:
        return 24
    if adx >= 22:
        return 16
    if adx >= 18:
        return 8

    return 0


def _calculate_structure_score(df: pd.DataFrame, lookback: int = 20) -> tuple[int, str]:
    """
    Oddiy swing structure:
    - oxirgi high oldingi highlardan yuqoriroq bo'lsa bullish
    - oxirgi low oldingi lowlardan pastroq bo'lsa bearish

    Bu professional market structure emas, lekin regime uchun yetarli boshlang'ich filtr.
    """

    if df is None or df.empty:
        return 0, "UNKNOWN"

    if "high" not in df.columns or "low" not in df.columns or "close" not in df.columns:
        return 0, "UNKNOWN"

    data = df.tail(lookback + 5)

    if len(data) < lookback:
        return 0, "UNKNOWN"

    recent_high = _safe_float(data["high"].iloc[-1])
    recent_low = _safe_float(data["low"].iloc[-1])

    previous_high = _safe_float(data["high"].iloc[:-1].max())
    previous_low = _safe_float(data["low"].iloc[:-1].min())

    if recent_high > previous_high and recent_low > previous_low:
        return 20, "UP"

    if recent_low < previous_low and recent_high < previous_high:
        return 20, "DOWN"

    closes = data["close"].tail(10)

    if closes.iloc[-1] > closes.iloc[0]:
        return 10, "UP"

    if closes.iloc[-1] < closes.iloc[0]:
        return 10, "DOWN"

    return 0, "RANGE"


def detect_market_regime(
    df: pd.DataFrame,
    *,
    ema_column: str = "EMA_50",
    atr_column: str = "ATR",
    adx_column: str = "ADX",
) -> MarketRegimeResult:
    """
    Bozor holatini aniqlaydi.

    Bu modul signal bermaydi.
    Faqat shuni aytadi:
    - bozor trenddami?
    - qaysi tomonga?
    - volatility normalmi?
    - chop/range xavfi bormi?
    """

    if df is None or df.empty:
        return MarketRegimeResult(
            regime="UNKNOWN",
            trend_direction="UNKNOWN",
            trend_strength=0,
            volatility_state="UNKNOWN",
            atr_percentile=0.0,
            ema_slope_score=0,
            adx_score=0,
            structure_score=0,
            reason="Dataframe empty",
        )

    atr_percentile = _calculate_atr_percentile(df, atr_column=atr_column)
    ema_slope_score, ema_direction = _calculate_ema_slope_score(df, ema_column=ema_column)
    adx_score = _calculate_adx_score(df, adx_column=adx_column)
    structure_score, structure_direction = _calculate_structure_score(df)

    if atr_percentile >= 0.90:
        volatility_state = "HIGH_VOLATILITY"
    elif atr_percentile >= 0.70:
        volatility_state = "ELEVATED_VOLATILITY"
    elif atr_percentile <= 0.20 and atr_percentile > 0:
        volatility_state = "LOW_VOLATILITY"
    else:
        volatility_state = "NORMAL_VOLATILITY"

    direction_votes = {
        "UP": 0,
        "DOWN": 0,
        "RANGE": 0,
        "UNKNOWN": 0,
    }

    direction_votes[ema_direction] = direction_votes.get(ema_direction, 0) + 1
    direction_votes[structure_direction] = direction_votes.get(structure_direction, 0) + 1

    if direction_votes["UP"] > direction_votes["DOWN"]:
        trend_direction = "UP"
    elif direction_votes["DOWN"] > direction_votes["UP"]:
        trend_direction = "DOWN"
    else:
        trend_direction = "RANGE"

    trend_strength = _clamp(ema_slope_score + adx_score + structure_score)

    # ---------------------------------------------------------
    # FINAL REGIME DECISION
    # ---------------------------------------------------------
    # Oldingi thresholdlar juda qattiq edi:
    # TRENDING uchun 55 kerak bo'lgani sabab backtestda TRENDING_UP/DOWN deyarli chiqmay qoldi.
    # Endi trend_strength >= 45 bo'lsa trend deb qabul qilamiz.
    # HIGH_VOLATILITY faqat trend juda kuchsiz bo'lsa bloklovchi risk bo'ladi.
    
    if volatility_state == "HIGH_VOLATILITY" and trend_strength < 45:
        regime = "HIGH_VOLATILITY_RISK"

    elif trend_strength >= 45 and trend_direction == "UP":
        regime = "TRENDING_UP"

    elif trend_strength >= 45 and trend_direction == "DOWN":
        regime = "TRENDING_DOWN"

    elif trend_strength <= 15 and volatility_state == "LOW_VOLATILITY":
        regime = "LOW_LIQUIDITY_CHOP"

    elif trend_strength <= 25:
        regime = "RANGING"

    else:
        regime = "MIXED"

    reason = (
        f"Regime={regime}; Direction={trend_direction}; "
        f"TrendStrength={trend_strength}; Volatility={volatility_state}; "
        f"ATRPercentile={atr_percentile}; EMA={ema_direction}/{ema_slope_score}; "
        f"ADXScore={adx_score}; Structure={structure_direction}/{structure_score}"
    )

    return MarketRegimeResult(
        regime=regime,
        trend_direction=trend_direction,
        trend_strength=trend_strength,
        volatility_state=volatility_state,
        atr_percentile=atr_percentile,
        ema_slope_score=ema_slope_score,
        adx_score=adx_score,
        structure_score=structure_score,
        reason=reason,
    )