from config import (
    STATUS_READY_BUY,
    STATUS_READY_SELL,
    ENABLE_MARKET_REGIME_FILTER,
    ENABLE_TREND_DIRECTION_FILTER,
    ENABLE_QUALITY_SCORE_FILTER,
    ENABLE_CONFLICT_SCORE_FILTER,
    ENABLE_ENTRY_QUALITY_FILTER,
    MIN_QUALITY_SCORE,
    MAX_CONFLICT_SCORE,
    MIN_ENTRY_QUALITY_SCORE,
    ENABLE_LIVE_SAFETY_FILTER,
    LIVE_MIN_QUALITY_SCORE,
    LIVE_MIN_ENTRY_QUALITY_SCORE,
    LIVE_MAX_CONFLICT_SCORE,
    LIVE_ALLOW_MIXED_REGIME,
    LIVE_ALLOW_TRENDING_UP,
    LIVE_ALLOW_TRENDING_DOWN,
    LIVE_ALLOW_RANGING,
    LIVE_ALLOW_HIGH_VOLATILITY_RISK,
    LIVE_ALLOW_LOW_LIQUIDITY_CHOP,
)

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

from signal_quality import evaluate_signal_quality
from market_regime import detect_market_regime


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
        h1_bias == "BULLISH" and m15_bias == "BULLISH" and d1_bias != "BEARISH"
    )

    bearish_exec_ok = (
        h1_bias == "BEARISH" and m15_bias == "BEARISH" and d1_bias != "BULLISH"
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
        alignment_text = (
            "H1 + M15 bullish, lekin D1 bearish. Higher-timeframe conflict."
        )
    elif h1_bias == "BEARISH" and m15_bias == "BEARISH" and d1_bias == "BULLISH":
        alignment_text = (
            "H1 + M15 bearish, lekin D1 bullish. Higher-timeframe conflict."
        )
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
    market_regime: str = "MIXED",
    confluence_score: int = 0,
    min_risk_reward: float = 0.8,  # <--- YANGI: Skalping uchun minimum risk
    confluence_min_score: int = 7,
) -> dict:
    """
    Live analyzer va backtester uchun yagona signal pipeline.
    PRO SCALPER + MARKET REGIME mantiqi shu yerda ishlaydi.
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

    trade_plan = generate_trade_plan(setup_status, signal_strength, price_location)

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
    market_regime = str(market_regime or "MIXED").upper()

    tp1, tp2, tp3 = calculate_multi_tp(
        setup_status,
        suggested_entry,
        suggested_sl,
        atr_value,
        market_regime,
    )

    # Skalping uchun eng yaqin ishonchli nuqta TP1 ni asosiy TP qilamiz
    if tp1 is not None:
        suggested_tp = tp1

    risk_reward_ratio = calculate_risk_reward(
        setup_status,
        suggested_entry,
        suggested_sl,
        suggested_tp,
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
    block_reason = ""

    # ---------------------------------------------------------
    # 3. MARKET REGIME FILTER
    # ---------------------------------------------------------
    regime_block_reasons = []

    if ENABLE_MARKET_REGIME_FILTER:
        if market_regime == "HIGH_VOLATILITY_RISK":
            regime_block_reasons.append(
                "WAIT: Market regime HIGH_VOLATILITY_RISK. Volatility juda yuqori, signal bloklandi."
            )

        if market_regime == "LOW_LIQUIDITY_CHOP":
            regime_block_reasons.append(
                "WAIT: Market regime LOW_LIQUIDITY_CHOP. Bozor sust/chop, signal bloklandi."
            )

        if market_regime == "RANGING" and setup_status in [
            STATUS_READY_BUY,
            STATUS_READY_SELL,
        ]:
            regime_block_reasons.append(
                "WAIT: Market regime RANGING. Trend-following READY signal range bozorida bloklandi."
            )

    if ENABLE_TREND_DIRECTION_FILTER:
        if market_regime == "TRENDING_UP" and final_signal == "SELL":
            regime_block_reasons.append(
                "WAIT: Market regime TRENDING_UP. SELL signal trendga qarshi bo‘lgani uchun bloklandi."
            )

        if market_regime == "TRENDING_DOWN" and final_signal == "BUY":
            regime_block_reasons.append(
                "WAIT: Market regime TRENDING_DOWN. BUY signal trendga qarshi bo‘lgani uchun bloklandi."
            )

    if regime_block_reasons:
        final_signal = "WAIT"
        block_reason = "MARKET_REGIME"
        reason = " ".join(regime_block_reasons)

    if final_signal in ["BUY", "SELL"]:
        if risk_reward_ratio is None or risk_reward_ratio < min_risk_reward:
            final_signal = "WAIT"
            block_reason = "RISK_REWARD"
            reason = (
                f"WAIT: Risk/Reward past ({risk_reward_ratio if risk_reward_ratio is not None else 'N/A'}). "
                f"Minimum {min_risk_reward} kerak."
            )

    if final_signal in ["BUY", "SELL"] and confluence_score < confluence_min_score:
        final_signal = "WAIT"
        block_reason = "CONFLUENCE"
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

    alert_message = generate_alert_message(final_signal, setup_status, signal_strength)

    quality = evaluate_signal_quality(
        final_signal=final_signal,
        h1_trend=h1_trend,
        m15_trend=m15_trend,
        d1_trend="",
        rsi_text=rsi_text,
        macd_text=macd_text,
        candle_confirmation=candle_confirmation,
        price_location=price_location,
        entry_zone_text=entry_zone_text,
        market_structure="",
        fvg_text=entry_zone_text,
        order_block="",
        liquidity_zones="",
        wyckoff_phase="",
        suggested_entry=suggested_entry,
        suggested_sl=suggested_sl,
        suggested_tp=suggested_tp,
        current_price=current_price,
        atr_value=atr_value,
        risk_reward_ratio=risk_reward_ratio,
        support=support,
        resistance=resistance,
    )

    # ---------------------------------------------------------
    # 4. QUALITY SCORE FILTER
    # ---------------------------------------------------------
    if (
        ENABLE_QUALITY_SCORE_FILTER
        and final_signal in ["BUY", "SELL"]
        and quality.quality_score < MIN_QUALITY_SCORE
    ):
        final_signal = "WAIT"
        block_reason = "QUALITY_SCORE"
        reason = (
            f"WAIT: Quality score past ({quality.quality_score}/100). "
            f"Minimum {MIN_QUALITY_SCORE} kerak. {quality.quality_text}"
        )

    # ---------------------------------------------------------
    # 5. CONFLICT SCORE FILTER
    # ---------------------------------------------------------
    if (
        ENABLE_CONFLICT_SCORE_FILTER
        and final_signal in ["BUY", "SELL"]
        and quality.conflict_score >= MAX_CONFLICT_SCORE
    ):
        final_signal = "WAIT"
        block_reason = "CONFLICT"
        reason = (
            f"WAIT: Conflict score yuqori ({quality.conflict_score}). "
            f"Maximum {MAX_CONFLICT_SCORE} dan past bo‘lishi kerak. "
            f"BUY va SELL dalillari aralashib ketgan. {quality.quality_text}"
        )
        alert_message = generate_alert_message(
            final_signal, setup_status, signal_strength
        )

    # ---------------------------------------------------------
    # 6. ENTRY QUALITY FILTER
    # ---------------------------------------------------------
    if (
        ENABLE_ENTRY_QUALITY_FILTER
        and final_signal in ["BUY", "SELL"]
        and quality.entry_quality_score < MIN_ENTRY_QUALITY_SCORE
    ):
        final_signal = "WAIT"
        block_reason = "ENTRY_QUALITY"
        reason = (
            f"WAIT: Entry quality past ({quality.entry_quality_score}/100). "
            f"Minimum {MIN_ENTRY_QUALITY_SCORE} kerak. "
            f"Entry grade: {quality.entry_quality_grade}. {quality.quality_text}"
        )
        alert_message = generate_alert_message(
            final_signal, setup_status, signal_strength
        )

    quality = evaluate_signal_quality(
        final_signal=final_signal,
        h1_trend=h1_trend,
        m15_trend=m15_trend,
        d1_trend="",
        rsi_text=rsi_text,
        macd_text=macd_text,
        candle_confirmation=candle_confirmation,
        price_location=price_location,
        entry_zone_text=entry_zone_text,
        market_structure="",
        fvg_text=entry_zone_text,
        order_block="",
        liquidity_zones="",
        wyckoff_phase="",
        suggested_entry=suggested_entry,
        suggested_sl=suggested_sl,
        suggested_tp=suggested_tp,
        current_price=current_price,
        atr_value=atr_value,
        risk_reward_ratio=risk_reward_ratio,
        support=support,
        resistance=resistance,
    )

    # ---------------------------------------------------------
    # 7. LIVE / DEMO SAFETY FILTER
    # ---------------------------------------------------------
    if ENABLE_LIVE_SAFETY_FILTER and final_signal in ["BUY", "SELL"]:
        allowed_regime = False

        if market_regime == "MIXED" and LIVE_ALLOW_MIXED_REGIME:
            allowed_regime = True
        elif market_regime == "TRENDING_UP" and LIVE_ALLOW_TRENDING_UP:
            allowed_regime = True
        elif market_regime == "TRENDING_DOWN" and LIVE_ALLOW_TRENDING_DOWN:
            allowed_regime = True
        elif market_regime == "RANGING" and LIVE_ALLOW_RANGING:
            allowed_regime = True
        elif (
            market_regime == "HIGH_VOLATILITY_RISK" and LIVE_ALLOW_HIGH_VOLATILITY_RISK
        ):
            allowed_regime = True
        elif market_regime == "LOW_LIQUIDITY_CHOP" and LIVE_ALLOW_LOW_LIQUIDITY_CHOP:
            allowed_regime = True

        if not allowed_regime:
            final_signal = "WAIT"
            block_reason = "LIVE_REGIME_SAFETY"
            reason = f"WAIT: Live safety filter. Market regime {market_regime} live/demo uchun ruxsat emas."
            alert_message = generate_alert_message(
                final_signal, setup_status, signal_strength
            )

        elif quality.quality_score < LIVE_MIN_QUALITY_SCORE:
            final_signal = "WAIT"
            block_reason = "LIVE_QUALITY_SAFETY"
            reason = (
                f"WAIT: Live quality safety. Quality {quality.quality_score}/100. "
                f"Minimum {LIVE_MIN_QUALITY_SCORE} kerak."
            )
            alert_message = generate_alert_message(
                final_signal, setup_status, signal_strength
            )

        elif quality.entry_quality_score < LIVE_MIN_ENTRY_QUALITY_SCORE:
            final_signal = "WAIT"
            block_reason = "LIVE_ENTRY_SAFETY"
            reason = (
                f"WAIT: Live entry safety. Entry quality {quality.entry_quality_score}/100. "
                f"Minimum {LIVE_MIN_ENTRY_QUALITY_SCORE} kerak."
            )
            alert_message = generate_alert_message(
                final_signal, setup_status, signal_strength
            )

        elif quality.conflict_score > LIVE_MAX_CONFLICT_SCORE:
            final_signal = "WAIT"
            block_reason = "LIVE_CONFLICT_SAFETY"
            reason = (
                f"WAIT: Live conflict safety. Conflict {quality.conflict_score}. "
                f"Maximum {LIVE_MAX_CONFLICT_SCORE} bo‘lishi kerak."
            )
            alert_message = generate_alert_message(
                final_signal, setup_status, signal_strength
            )

            quality = evaluate_signal_quality(
                final_signal=final_signal,
                h1_trend=h1_trend,
                m15_trend=m15_trend,
                d1_trend="",
                rsi_text=rsi_text,
                macd_text=macd_text,
                candle_confirmation=candle_confirmation,
                price_location=price_location,
                entry_zone_text=entry_zone_text,
                market_structure="",
                fvg_text=entry_zone_text,
                order_block="",
                liquidity_zones="",
                wyckoff_phase="",
                suggested_entry=suggested_entry,
                suggested_sl=suggested_sl,
                suggested_tp=suggested_tp,
                current_price=current_price,
                atr_value=atr_value,
                risk_reward_ratio=risk_reward_ratio,
                support=support,
                resistance=resistance,
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
        "market_regime": market_regime,
        "regime_direction": "",
        "regime_strength": "",
        "volatility_state": "",
        "atr_percentile": "",
        "regime_reason": f"Manual/input market regime: {market_regime}",
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "trailing_sl": trailing_sl,
        "breakeven_sl": breakeven_sl,
        "breakeven_active": breakeven_active,
        "final_signal": final_signal,
        "reason": reason,
        "block_reason": block_reason,
        "alert_message": alert_message,
        "quality_score": quality.quality_score,
        "quality_grade": quality.quality_grade,
        "quality_text": quality.quality_text,
        "buy_score": quality.buy_score,
        "sell_score": quality.sell_score,
        "conflict_score": quality.conflict_score,
        "net_bias": quality.net_bias,
        "entry_quality_score": quality.entry_quality_score,
        "entry_quality_grade": quality.entry_quality_grade,
        "enable_market_regime_filter": ENABLE_MARKET_REGIME_FILTER,
        "enable_trend_direction_filter": ENABLE_TREND_DIRECTION_FILTER,
        "enable_quality_score_filter": ENABLE_QUALITY_SCORE_FILTER,
        "enable_conflict_score_filter": ENABLE_CONFLICT_SCORE_FILTER,
        "enable_entry_quality_filter": ENABLE_ENTRY_QUALITY_FILTER,
        "min_quality_score": MIN_QUALITY_SCORE,
        "max_conflict_score": MAX_CONFLICT_SCORE,
        "min_entry_quality_score": MIN_ENTRY_QUALITY_SCORE,
        "enable_live_safety_filter": ENABLE_LIVE_SAFETY_FILTER,
        "live_min_quality_score": LIVE_MIN_QUALITY_SCORE,
        "live_min_entry_quality_score": LIVE_MIN_ENTRY_QUALITY_SCORE,
        "live_max_conflict_score": LIVE_MAX_CONFLICT_SCORE,
        "live_allow_mixed_regime": LIVE_ALLOW_MIXED_REGIME,
        "live_allow_trending_up": LIVE_ALLOW_TRENDING_UP,
        "live_allow_trending_down": LIVE_ALLOW_TRENDING_DOWN,
        "live_allow_ranging": LIVE_ALLOW_RANGING,
        "live_allow_high_volatility_risk": LIVE_ALLOW_HIGH_VOLATILITY_RISK,
        "live_allow_low_liquidity_chop": LIVE_ALLOW_LOW_LIQUIDITY_CHOP,
    }
