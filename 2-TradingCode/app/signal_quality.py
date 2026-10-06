from dataclasses import dataclass


@dataclass
class SignalQualityResult:
    buy_score: int
    sell_score: int
    conflict_score: int
    net_bias: int
    entry_quality_score: int
    entry_quality_grade: str
    quality_score: int
    quality_grade: str
    quality_text: str


def _text(value) -> str:
    return str(value or "").lower()


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _grade(score: int) -> str:
    if score >= 80:
        return "HIGH QUALITY"
    if score >= 65:
        return "VALID"
    if score >= 50:
        return "WATCH"
    return "WEAK"


def _entry_grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def calculate_direction_scores(
    h1_trend: str,
    m15_trend: str,
    d1_trend: str = "",
    rsi_text: str = "",
    macd_text: str = "",
    candle_confirmation: str = "",
    price_location: str = "",
    entry_zone_text: str = "",
    market_structure: str = "",
    fvg_text: str = "",
    order_block: str = "",
    liquidity_zones: str = "",
    wyckoff_phase: str = "",
):
    """
    BUY va SELL dalillarini alohida hisoblaydi.

    Maqsad:
    - bullish va bearish signallar aralashib ketmasin
    - qaysi tomonda kuch borligini alohida ko'rish
    - qarama-qarshi signal bo'lsa conflict aniqlash
    """

    buy_score = 0
    sell_score = 0

    h1 = _text(h1_trend)
    m15 = _text(m15_trend)
    d1 = _text(d1_trend)
    rsi = _text(rsi_text)
    macd = _text(macd_text)
    candle = _text(candle_confirmation)
    price = _text(price_location)
    zone = _text(entry_zone_text)
    structure = _text(market_structure)
    fvg = _text(fvg_text)
    ob = _text(order_block)
    liquidity = _text(liquidity_zones)
    wyckoff = _text(wyckoff_phase)

    # 1) Trend score
    if "bull" in d1:
        buy_score += 12
    elif "bear" in d1:
        sell_score += 12

    if "bull" in h1:
        buy_score += 15
    elif "bear" in h1:
        sell_score += 15

    if "bull" in m15:
        buy_score += 10
    elif "bear" in m15:
        sell_score += 10

    # 2) Momentum confirmation
    if "bull" in macd or "buy" in macd:
        buy_score += 8
    elif "bear" in macd or "sell" in macd:
        sell_score += 8

    if "oversold" in rsi or "bull" in rsi or "buy" in rsi:
        buy_score += 5
    elif "overbought" in rsi or "bear" in rsi or "sell" in rsi:
        sell_score += 5

    # 3) Candle confirmation
    if "bullish" in candle or "buy" in candle:
        buy_score += 12
    if "bearish" in candle or "sell" in candle:
        sell_score += 12

    if "engulfing" in candle:
        buy_score += 4
        sell_score += 4

    if "sweep" in candle:
        buy_score += 3
        sell_score += 3

    # 4) Entry zone / price location
    if "support" in price:
        buy_score += 6
    if "resistance" in price:
        sell_score += 6

    if "bullish fvg" in zone or "bullish fvg" in fvg:
        buy_score += 8
    if "bearish fvg" in zone or "bearish fvg" in fvg:
        sell_score += 8

    if "demand" in ob or "bullish" in ob:
        buy_score += 7
    if "supply" in ob or "bearish" in ob:
        sell_score += 7

    # 5) Market structure
    if "hh" in structure or "hl" in structure or "bull" in structure:
        buy_score += 10
    if "ll" in structure or "lh" in structure or "bear" in structure:
        sell_score += 10

    # 6) Liquidity
    if "buy-side swept" in liquidity or "sell liquidity swept" in liquidity:
        buy_score += 6
    if "sell-side swept" in liquidity or "buy liquidity swept" in liquidity:
        sell_score += 6

    # 7) Wyckoff
    if "accumulation" in wyckoff or "markup" in wyckoff:
        buy_score += 5
    if "distribution" in wyckoff or "markdown" in wyckoff:
        sell_score += 5

    # Conflict: BUY va SELL ikkalasi ham kuchli bo'lsa xavf oshadi
    conflict_score = min(buy_score, sell_score)
    net_bias = buy_score - sell_score

    return buy_score, sell_score, conflict_score, net_bias


def calculate_entry_quality(
    final_signal: str,
    suggested_entry,
    suggested_sl,
    suggested_tp,
    current_price,
    atr_value,
    risk_reward_ratio,
    support=None,
    resistance=None,
):
    """
    Entry sifatini 0-100 oralig'ida baholaydi.

    Bu signal direction emas.
    Bu faqat kirish joyi yaxshi yoki yomonligini tekshiradi.
    """

    score = 0

    signal = str(final_signal or "").upper()

    entry = _safe_float(suggested_entry)
    sl = _safe_float(suggested_sl)
    tp = _safe_float(suggested_tp)
    price = _safe_float(current_price)
    atr = _safe_float(atr_value, 0)
    rr = _safe_float(risk_reward_ratio)

    if signal not in ["BUY", "SELL", "WAIT"]:
        return 0, "D"

    if entry is None or sl is None or tp is None:
        return 0, "D"

    # 1) RR sifati
    if rr is not None:
        if rr >= 2.0:
            score += 30
        elif rr >= 1.5:
            score += 24
        elif rr >= 1.0:
            score += 12
        else:
            score += 0

    # 2) SL masofasi ATR bilan mantiqli bo'lishi kerak
    if atr and atr > 0:
        sl_distance = abs(entry - sl)
        if 0.4 * atr <= sl_distance <= 2.5 * atr:
            score += 25
        elif 0.25 * atr <= sl_distance <= 3.5 * atr:
            score += 12

    # 3) Entry joriy narxga haddan tashqari uzoq bo'lmasin
    if price is not None and atr and atr > 0:
        entry_distance = abs(price - entry)
        if entry_distance <= 0.5 * atr:
            score += 20
        elif entry_distance <= 1.0 * atr:
            score += 10

    # 4) Direction bo'yicha SL/TP joylashuvi to'g'rimi?
    if signal == "BUY":
        if sl < entry < tp:
            score += 15

    elif signal == "SELL":
        if tp < entry < sl:
            score += 15

    else:
        # WAIT bo'lsa ham entry structure to'g'riligini ko'rish uchun kam ball
        if sl != entry and tp != entry:
            score += 5

    # 5) Support/resistance yaqinligi
    sup = _safe_float(support)
    res = _safe_float(resistance)

    if atr and atr > 0:
        if signal == "BUY" and sup is not None:
            if abs(entry - sup) <= atr:
                score += 10

        if signal == "SELL" and res is not None:
            if abs(entry - res) <= atr:
                score += 10

    score = _clamp(score)
    return score, _entry_grade(score)


def evaluate_signal_quality(
    *,
    final_signal: str,
    h1_trend: str,
    m15_trend: str,
    d1_trend: str = "",
    rsi_text: str = "",
    macd_text: str = "",
    candle_confirmation: str = "",
    price_location: str = "",
    entry_zone_text: str = "",
    market_structure: str = "",
    fvg_text: str = "",
    order_block: str = "",
    liquidity_zones: str = "",
    wyckoff_phase: str = "",
    suggested_entry=None,
    suggested_sl=None,
    suggested_tp=None,
    current_price=None,
    atr_value=None,
    risk_reward_ratio=None,
    support=None,
    resistance=None,
) -> SignalQualityResult:
    """
    Umumiy signal quality bahosi.

    Bu funksiya hozircha signalni bloklamaydi.
    Faqat baholaydi va journalga yozish uchun result qaytaradi.
    """

    buy_score, sell_score, conflict_score, net_bias = calculate_direction_scores(
        h1_trend=h1_trend,
        m15_trend=m15_trend,
        d1_trend=d1_trend,
        rsi_text=rsi_text,
        macd_text=macd_text,
        candle_confirmation=candle_confirmation,
        price_location=price_location,
        entry_zone_text=entry_zone_text,
        market_structure=market_structure,
        fvg_text=fvg_text,
        order_block=order_block,
        liquidity_zones=liquidity_zones,
        wyckoff_phase=wyckoff_phase,
    )

    entry_quality_score, entry_quality_grade = calculate_entry_quality(
        final_signal=final_signal,
        suggested_entry=suggested_entry,
        suggested_sl=suggested_sl,
        suggested_tp=suggested_tp,
        current_price=current_price,
        atr_value=atr_value,
        risk_reward_ratio=risk_reward_ratio,
        support=support,
        resistance=resistance,
    )

    signal = str(final_signal or "").upper()

    if signal == "BUY":
        directional_strength = max(0, buy_score - sell_score)
    elif signal == "SELL":
        directional_strength = max(0, sell_score - buy_score)
    else:
        directional_strength = max(buy_score, sell_score) // 2

    # Conflict qancha katta bo'lsa, final quality shuncha tushadi
    raw_quality = directional_strength + entry_quality_score - conflict_score

    quality_score = _clamp(raw_quality)
    quality_grade = _grade(quality_score)

    quality_text = (
        f"QUALITY: {quality_score}/100 — {quality_grade} | "
        f"BUY {buy_score} / SELL {sell_score} / Conflict {conflict_score} | "
        f"Entry {entry_quality_score}/100 ({entry_quality_grade})"
    )

    return SignalQualityResult(
        buy_score=buy_score,
        sell_score=sell_score,
        conflict_score=conflict_score,
        net_bias=net_bias,
        entry_quality_score=entry_quality_score,
        entry_quality_grade=entry_quality_grade,
        quality_score=quality_score,
        quality_grade=quality_grade,
        quality_text=quality_text,
    )