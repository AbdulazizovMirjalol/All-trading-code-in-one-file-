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
    h1_bias = _trend_bias(h1_trend)
    m15_bias = _trend_bias(m15_trend)

    # AGRESSIV BOT UCHUN: Faqat H1 va M15 ni tekshiramiz, D1 ga qaramaymiz
    bullish_exec_ok = (h1_bias == "BULLISH" and m15_bias == "BULLISH")
    bearish_exec_ok = (h1_bias == "BEARISH" and m15_bias == "BEARISH")

    alignment_ok = bullish_exec_ok or bearish_exec_ok

    if bullish_exec_ok:
        alignment_text = "H1 + M15 bullish alignment (Intraday tasdiqlandi)."
    elif bearish_exec_ok:
        alignment_text = "H1 + M15 bearish alignment (Intraday tasdiqlandi)."
    else:
        alignment_text = "H1 va M15 bir tomonda emas. Entry alignment yo'q."

    updated_signal = final_signal
    updated_reason = reason

    if final_signal == "BUY" and not bullish_exec_ok:
        updated_signal = "WAIT"
        block_reason = "WAIT: Intraday alignment mos emas. BUY uchun H1 + M15 bullish bo'lishi kerak."
        updated_reason = block_reason if not reason else f"{block_reason} | {reason}"

    elif final_signal == "SELL" and not bearish_exec_ok:
        updated_signal = "WAIT"
        block_reason = "WAIT: Intraday alignment mos emas. SELL uchun H1 + M15 bearish bo'lishi kerak."
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
    confluence_score: int = 0,
    min_risk_reward: float = 1.5,
    confluence_min_score: int = 7,
) -> dict:
    """
    Live analyzer va backtester uchun yagona signal pipeline.
    Bu yerda setup -> RR -> confluence -> final decision bir joyda boshqariladi.
    """

    setup_status = detect_setup_status(
        h1_trend,
        m15_trend,
        rsi_text,
        macd_text,
        price_location,
        entry_zone_text,
        candle_confirmation,
    )

    trade_comment = generate_trade_comment(
        h1_trend,
        m15_trend,
        rsi_text,
        macd_text,
        price_location,
        entry_zone_text,
        setup_status,
    )

    signal_strength = detect_signal_strength(
        h1_trend,
        m15_trend,
        rsi_text,
        macd_text,
        setup_status,
        candle_confirmation,
    )

    trade_plan = generate_trade_plan(
        setup_status,
        signal_strength,
        price_location,
    )

    summary = generate_summary(
        h1_trend,
        m15_trend,
        last_rsi,
        macd_text,
        current_price,
        support,
        resistance,
    )

    suggested_entry = generate_entry_price(
        setup_status=setup_status,
        current_price=current_price,
        ema20_value=ema20_value,
        support=support,
        resistance=resistance,
        atr_value=atr_value,
        entry_zone_text=entry_zone_text,
    )

    suggested_sl, suggested_tp = generate_risk_levels(
        setup_status=setup_status,
        current_price=current_price,
        suggested_entry=suggested_entry,
        support=support,
        resistance=resistance,
        atr_value=atr_value,
        entry_zone_text=entry_zone_text,
    )

    if suggested_entry is not None and suggested_sl is not None:
        risk = abs(suggested_entry - suggested_sl)

        if risk > 0:
            if suggested_tp is None:
                if setup_status == STATUS_READY_BUY:
                    suggested_tp = round(suggested_entry + risk * 1.8, 2)
                elif setup_status == STATUS_READY_SELL:
                    suggested_tp = round(suggested_entry - risk * 1.8, 2)

    risk_reward_ratio = calculate_risk_reward(
        setup_status,
        suggested_entry,
        suggested_sl,
        suggested_tp,
    )

    if suggested_entry is not None and suggested_sl is not None:
        risk = abs(suggested_entry - suggested_sl)

        if risk > 0 and (risk_reward_ratio is None or risk_reward_ratio < 1.5):
            if setup_status == STATUS_READY_BUY:
                rr_floor_tp = round(suggested_entry + risk * 2.0, 2)
                if suggested_tp is None:
                    suggested_tp = rr_floor_tp
                else:
                    suggested_tp = round(max(suggested_tp, rr_floor_tp), 2)

            elif setup_status == STATUS_READY_SELL:
                rr_floor_tp = round(suggested_entry - risk * 2.0, 2)
                if suggested_tp is None:
                    suggested_tp = rr_floor_tp
                else:
                    suggested_tp = round(min(suggested_tp, rr_floor_tp), 2)

            risk_reward_ratio = calculate_risk_reward(
                setup_status,
                suggested_entry,
                suggested_sl,
                suggested_tp,
            )

    tp1, tp2, tp3 = calculate_multi_tp(
        setup_status,
        suggested_entry,
        suggested_sl,
        atr_value,
    )

    trailing_sl = calculate_trailing_stop(
        setup_status,
        suggested_entry,
        current_price,
        atr_value,
    )

    breakeven_sl, breakeven_active = calculate_breakeven_level(
        setup_status,
        suggested_entry,
        tp1,
        current_price,
    )

    final_signal = generate_final_signal(
        setup_status,
        signal_strength,
        candle_confirmation,
        risk_reward_ratio,
    )

    reason = ""

    if final_signal in ["BUY", "SELL"]:
        if risk_reward_ratio is None or risk_reward_ratio < min_risk_reward:
            final_signal = "WAIT"
            reason = (
                f"WAIT: Risk/Reward past "
                f"({risk_reward_ratio if risk_reward_ratio is not None else 'N/A'}). "
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
            h1_trend,
            m15_trend,
            rsi_text,
            macd_text,
            price_location,
            entry_zone_text,
            setup_status,
            final_signal,
            risk_reward_ratio,
            candle_confirmation,
            signal_strength,
        )

    alert_message = generate_alert_message(
        final_signal,
        setup_status,
        signal_strength,
    )

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