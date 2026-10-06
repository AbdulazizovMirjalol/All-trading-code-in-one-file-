from config import STATUS_READY_BUY, STATUS_READY_SELL

from indicators import (
    detect_setup_status,
    generate_trade_comment,
    detect_signal_strength,
    generate_trade_plan,
    generate_summary,
    generate_entry_price,
    generate_risk_levels,
    calculate_risk_reward,
    generate_final_signal,
    calculate_multi_tp,
    calculate_trailing_stop,
    calculate_breakeven_level,
    generate_reason,
    generate_alert_message,
)

def _trend_bias(trend_text: str) -> str:
    text = str(trend_text).lower()

    if "bull" in text:
        return "BULLISH"
    if "bear" in text:
        return "BEARISH"

    return "NEUTRAL"


def apply_three_tf_alignment(
    final_signal: str,
    d1_trend: str,
    h1_trend: str,
    m15_trend: str,
    reason: str = "",
):
    d1_bias = _trend_bias(d1_trend)
    h1_bias = _trend_bias(h1_trend)
    m15_bias = _trend_bias(m15_trend)

    bullish_exec_ok = (
        h1_bias == "BULLISH"
        and m15_bias == "BULLISH"
        and d1_bias != "BEARISH"
    )

    bearish_exec_ok = (
        h1_bias == "BEARISH"
        and m15_bias == "BEARISH"
        and d1_bias != "BULLISH"
    )

    alignment_ok = bullish_exec_ok or bearish_exec_ok

    if d1_bias == h1_bias == m15_bias == "BULLISH":
        alignment_text = "D1 + H1 + M15 bullish alignment to'liq."
    elif d1_bias == h1_bias == m15_bias == "BEARISH":
        alignment_text = "D1 + H1 + M15 bearish alignment to'liq."
    elif h1_bias == "BULLISH" and m15_bias == "BULLISH" and d1_bias == "NEUTRAL":
        alignment_text = "H1 + M15 bullish, D1 neutral. Tactical BUY ruxsat."
    elif h1_bias == "BEARISH" and m15_bias == "BEARISH" and d1_bias == "NEUTRAL":
        alignment_text = "H1 + M15 bearish, D1 neutral. Tactical SELL ruxsat."
    elif h1_bias == "BULLISH" and m15_bias == "BULLISH" and d1_bias == "BEARISH":
        alignment_text = "H1 + M15 bullish, lekin D1 bearish. Higher-timeframe conflict."
    elif h1_bias == "BEARISH" and m15_bias == "BEARISH" and d1_bias == "BULLISH":
        alignment_text = "H1 + M15 bearish, lekin D1 bullish. Higher-timeframe conflict."
    elif h1_bias != m15_bias:
        alignment_text = "H1 va M15 bir tomonda emas. Entry alignment yo'q."
    else:
        alignment_text = "3TF alignment noaniq."

    updated_signal = final_signal
    updated_reason = reason

    if final_signal == "BUY" and not bullish_exec_ok:
        updated_signal = "WAIT"
        block_reason = (
            "WAIT: 3TF alignment mos emas. BUY uchun H1 + M15 bullish bo'lishi "
            "va D1 bearish bo'lmasligi kerak."
        )
        updated_reason = block_reason if not reason else f"{block_reason} | {reason}"

    elif final_signal == "SELL" and not bearish_exec_ok:
        updated_signal = "WAIT"
        block_reason = (
            "WAIT: 3TF alignment mos emas. SELL uchun H1 + M15 bearish bo'lishi "
            "va D1 bullish bo'lmasligi kerak."
        )
        updated_reason = block_reason if not reason else f"{block_reason} | {reason}"

    return updated_signal, alignment_ok, alignment_text, updated_reason


def build_signal_package(
    h1_trend: str,
    m15_trend: str,
    last_rsi: float,
    rsi_text: str,
    macd_text: str,
    current_price: float,
    support: float,
    resistance: float,
    price_location: str,
    entry_zone_text: str,
    candle_confirmation: str,
    atr_value: float,
    ema20_value: float,
    market_regime: str = "Trending", # <--- YANGI: Bozor iqlimi datchigi
    confluence_score: int = 0,
    min_risk_reward: float = 0.8,    # <--- YANGI: Skalping uchun minimum risk
    confluence_min_score: int = 7,
) -> dict:
    """
    Live analyzer va backtester uchun yagona signal pipeline.
    PRO SCALPER + MARKET REGIME mantiqi shu yerda ishlaydi.
    """

    setup_status = detect_setup_status(
        h1_trend, m15_trend, rsi_text, macd_text,
        price_location, entry_zone_text, candle_confirmation,
    )

    trade_comment = generate_trade_comment(
        h1_trend, m15_trend, rsi_text, macd_text,
        price_location, entry_zone_text, setup_status,
    )

    signal_strength = detect_signal_strength(
        h1_trend, m15_trend, rsi_text, macd_text, setup_status, candle_confirmation,
    )

    trade_plan = generate_trade_plan(setup_status, signal_strength, price_location)

    summary = generate_summary(
        h1_trend, m15_trend, last_rsi, macd_text,
        current_price, support, resistance,
    )

    suggested_entry = generate_entry_price(
        setup_status=setup_status, current_price=current_price, ema20_value=ema20_value,
        support=support, resistance=resistance, atr_value=atr_value, entry_zone_text=entry_zone_text,
    )

    suggested_sl, suggested_tp = generate_risk_levels(
        setup_status=setup_status, current_price=current_price, suggested_entry=suggested_entry,
        support=support, resistance=resistance, atr_value=atr_value, entry_zone_text=entry_zone_text,
    )

    # ---------------------------------------------------------
    # 1. PULLBACK VA QOPQON QO'YISH (PRO SCALPER)
    # ---------------------------------------------------------
    if atr_value > 0 and setup_status in [STATUS_READY_BUY, STATUS_READY_SELL]:
        pullback_distance = round(atr_value * 0.3, 2)
        if setup_status == STATUS_READY_BUY and suggested_entry is not None:
            suggested_entry = round(suggested_entry - pullback_distance, 2)
        elif setup_status == STATUS_READY_SELL and suggested_entry is not None:
            suggested_entry = round(suggested_entry + pullback_distance, 2)

    # ---------------------------------------------------------
    # 2. MARKET REGIME (Bozor iqlimiga qarab aqlli TP)
    # ---------------------------------------------------------
    tp1, tp2, tp3 = calculate_multi_tp(
        setup_status,
        suggested_entry,
        suggested_sl,
        atr_value,
        market_regime, # Iqlim sensori ishga tushdi
    )

    # Skalping uchun eng yaqin ishonchli nuqta TP1 ni asosiy TP qilamiz
    if tp1 is not None:
        suggested_tp = tp1

    risk_reward_ratio = calculate_risk_reward(
        setup_status, suggested_entry, suggested_sl, suggested_tp,
    )

    trailing_sl = calculate_trailing_stop(
        setup_status, suggested_entry, current_price, atr_value,
    )

    breakeven_sl, breakeven_active = calculate_breakeven_level(
        setup_status, suggested_entry, tp1, current_price,
    )

    final_signal = generate_final_signal(
        setup_status, signal_strength, candle_confirmation, risk_reward_ratio,
    )

    reason = ""

    if final_signal in ["BUY", "SELL"]:
        if risk_reward_ratio is None or risk_reward_ratio < min_risk_reward:
            final_signal = "WAIT"
            reason = (
                f"WAIT: Risk/Reward past ({risk_reward_ratio if risk_reward_ratio is not None else 'N/A'}). "
                f"Minimum {min_risk_reward} kerak."
            )

    if final_signal in ["BUY", "SELL"] and confluence_score < confluence_min_score:
        final_signal = "WAIT"
        reason = (
            f"WAIT: Confluence score past ({confluence_score}/20). "
            f"Minimum {confluence_min_score} kerak."
        )

    if not reason:
        reason = generate_reason(
            h1_trend, m15_trend, rsi_text, macd_text, price_location, entry_zone_text,
            setup_status, final_signal, risk_reward_ratio, candle_confirmation, signal_strength,
        )

    alert_message = generate_alert_message(final_signal, setup_status, signal_strength)

    return {
        "setup_status": setup_status,
        "trade_comment": trade_comment,
        "signal_strength": signal_strength,
        "trade_plan": trade_plan,
        "summary": summary,
        "suggested_entry": suggested_entry,
        "suggested_sl": suggested_sl,
        "suggested_tp": suggested_tp,
        "risk_reward_ratio": risk_reward_ratio,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "trailing_sl": trailing_sl,
        "breakeven_sl": breakeven_sl,
        "breakeven_active": breakeven_active,
        "final_signal": final_signal,
        "reason": reason,
        "alert_message": alert_message,
    }