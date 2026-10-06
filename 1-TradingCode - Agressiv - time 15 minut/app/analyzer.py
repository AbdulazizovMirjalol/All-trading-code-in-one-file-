import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from signal_engine import build_signal_package, apply_three_tf_alignment
from config import (
    SYMBOL,
    EMA_FAST,
    EMA_SLOW,
    RSI_PERIOD,
    ATR_PERIOD,
    M15_BARS,
    H1_BARS,
    D1_BARS,
    M15_TIMEFRAME_NAME,
    H1_TIMEFRAME_NAME,
    SIGNAL_MODE,
    ENABLE_ML_FILTER,
    MIN_RISK_REWARD,
    STATUS_READY_BUY,
    STATUS_READY_SELL,
)

from mt5_client import get_gold_data

from indicators import (
    add_ema,
    detect_trend,
    add_rsi,
    interpret_rsi,
    generate_summary,
    add_macd,
    interpret_macd,
    find_support_resistance,
    analyze_timeframe_alignment,
    detect_price_location,
    detect_entry_zone,
    generate_trade_comment,
    add_atr,
    detect_setup_status,
    detect_signal_strength,
    generate_trade_plan,
    generate_risk_levels,
    calculate_risk_reward,
    generate_final_signal,
    generate_entry_price,
    generate_alert_message,
    generate_reason,
    detect_candle_confirmation,
    analyze_volume,
    get_session_status,
    is_good_session,
    add_stochastic_rsi,
    interpret_stochastic_rsi,
    detect_rsi_divergence,
    calculate_multi_tp,
    calculate_breakeven_level,
    calculate_trailing_stop,
    check_market_structure,
    detect_order_block,
    detect_liquidity_zones,
    detect_fair_value_gap_advanced,
    detect_breaker_block,
    detect_imbalance_fill,
    detect_wyckoff_phase,
    calculate_confluence_score,
)


def check_high_impact_news():
    """
    ForexFactory JSON feed dan HIGH impact USD yangiliklarini tekshiradi.
    Yangilikdan 30 daqiqa oldin va 30 daqiqa keyin bloklaydi.
    """
    try:
        import requests
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from config import TIMEZONE, NEWS_BLOCK_MINUTES_BEFORE, NEWS_BLOCK_MINUTES_AFTER

        now = datetime.now(ZoneInfo(TIMEZONE))
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return _news_fallback()

        events = response.json()

        high_impact_keywords = [
            "NFP", "Non-Farm", "FOMC", "Fed", "CPI", "GDP",
            "Interest Rate", "Unemployment", "Retail Sales",
            "PPI", "PCE", "ISM", "PMI", "Durable"
        ]

        for event in events:
            if str(event.get("impact", "")).lower() != "high":
                continue

            if str(event.get("country", "")).upper() != "USD":
                continue

            title = str(event.get("title", ""))
            if high_impact_keywords and not any(k.lower() in title.lower() for k in high_impact_keywords):
                continue

            event_time_str = event.get("date", "")
            if not event_time_str:
                continue

            try:
                event_time_utc = datetime.strptime(
                    event_time_str, "%Y-%m-%dT%H:%M:%S%z"
                )
                event_time_local = event_time_utc.astimezone(ZoneInfo(TIMEZONE))

                block_start = event_time_local - timedelta(minutes=NEWS_BLOCK_MINUTES_BEFORE)
                block_end = event_time_local + timedelta(minutes=NEWS_BLOCK_MINUTES_AFTER)

                if block_start <= now <= block_end:
                    return True, f"HIGH IMPACT: {title} ({event_time_local.strftime('%H:%M')} {TIMEZONE})"

            except Exception:
                continue

        return False, "Tinch vaqt — muhim yangilik yo'q"

    except Exception:
        return _news_fallback()


def _news_fallback():
    """
    Internet bo'lmasa vaqt asosida fallback himoya.
    O'zbekiston vaqti bo'yicha eng xavfli oralig'lar.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from config import TIMEZONE

    now = datetime.now(ZoneInfo(TIMEZONE))
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()  # Monday=0 ... Sunday=6
    day = now.day

    # Har oyning birinchi juma kuni NFP ga yaqin vaqt
    is_first_friday = (weekday == 4 and 1 <= day <= 7)

    # AQSH ma'lumotlari ko'p chiqadigan vaqt: 15:15 - 16:45 UZ
    if (hour == 15 and minute >= 15) or (hour == 16 and minute <= 45):
        if is_first_friday:
            return True, "FALLBACK: NFP / AQSH high-impact vaqti"
        return True, "FALLBACK: AQSH high-impact ma'lumotlari vaqti"

    # FOMC / Fed qarorlari odatda tun payti
    if (hour == 1 and minute >= 30) or (hour == 2 and minute <= 30):
        return True, "FALLBACK: FOMC / Fed vaqti"

    return False, "Tinch vaqt"


def get_d1_trend(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, D1_BARS)
    if rates is None or len(rates) < EMA_SLOW:
        return "NEUTRAL"

    df_d1 = pd.DataFrame(rates)
    df_d1["EMA_20"] = df_d1["close"].ewm(span=20, adjust=False).mean()
    df_d1["EMA_50"] = df_d1["close"].ewm(span=50, adjust=False).mean()

    ema20 = df_d1["EMA_20"].iloc[-1]
    ema50 = df_d1["EMA_50"].iloc[-1]
    close = df_d1["close"].iloc[-1]

    if close > ema20 > ema50:
        return "BULLISH"
    elif close < ema20 < ema50:
        return "BEARISH"
    else:
        return "NEUTRAL"


def get_dxy_status():
    from config import DXY_SYMBOL_CANDIDATES, ENABLE_DXY_FILTER

    if not ENABLE_DXY_FILTER:
        return "UNKNOWN"

    selected_symbol = None

    for candidate in DXY_SYMBOL_CANDIDATES:
        info = mt5.symbol_info(candidate)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(candidate, True)
            selected_symbol = candidate
            break

    if selected_symbol is None:
        return "UNKNOWN"

    rates = mt5.copy_rates_from_pos(selected_symbol, mt5.TIMEFRAME_M15, 0, 30)
    if rates is None or len(rates) < 20:
        return "UNKNOWN"

    df = pd.DataFrame(rates)
    df["EMA_10"] = df["close"].ewm(span=10, adjust=False).mean()
    df["EMA_20"] = df["close"].ewm(span=20, adjust=False).mean()

    ema10 = df["EMA_10"].iloc[-1]
    ema20 = df["EMA_20"].iloc[-1]

    if ema10 > ema20:
        return "STRENGTHENING"
    elif ema10 < ema20:
        return "WEAKENING"
    return "FLAT"


def _build_ml_payload(
    *,
    last_rsi,
    atr_value,
    confluence,
    risk_reward_ratio,
    suggested_entry,
    suggested_sl,
    suggested_tp,
    tp1,
    tp2,
    tp3,
    h1_trend,
    m15_trend,
    d1_trend,
    final_signal,
    setup_status,
    signal_strength,
    rsi_text,
    macd_text,
    candle_confirmation,
    stoch_rsi_text,
    session_status,
    dxy_status,
    is_news_time,
    news_reason,
    volume_status,
    fvg_data,
    order_block,
    breaker_block,
    liquidity_zones,
    imbalance_fill,
    wyckoff_phase,
    market_structure,
    divergence_text,
):
    actionable = "YES" if final_signal in ["BUY", "SELL"] else "NO"
    hot_signal = (
        "YES"
        if setup_status in [STATUS_READY_BUY, STATUS_READY_SELL]
        and str(signal_strength).upper().strip() == "STRONG"
        else "NO"
    )

    return {
        "rsi": last_rsi,
        "atr": atr_value,
        "confluence_score": confluence["score"],
        "risk_reward_ratio": risk_reward_ratio,
        "entry_price": suggested_entry,
        "stop_loss": suggested_sl,
        "take_profit": suggested_tp,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "ml_probability": 0.0,
        "h1_trend": h1_trend,
        "m15_trend": m15_trend,
        "d1_trend": d1_trend,
        "final_signal": final_signal,
        "setup_status": setup_status,
        "signal_strength": signal_strength,
        "actionable": actionable,
        "hot_signal": hot_signal,
        "ml_approved": True,
        "rsi_status": rsi_text,
        "macd_status": macd_text,
        "candle_confirmation": candle_confirmation,
        "stoch_rsi_signal": stoch_rsi_text,
        "session_status": session_status,
        "dxy_status": dxy_status,
        "news_blocked": is_news_time,
        "news_reason": news_reason,
        "volume_status": volume_status,
        "fvg_text": fvg_data["text"],
        "order_block": order_block,
        "breaker_block": breaker_block,
        "liquidity_zones": liquidity_zones,
        "imbalance_fill": imbalance_fill,
        "wyckoff_phase": wyckoff_phase,
        "market_structure": market_structure,
        "divergence_text": divergence_text,
    }


def run_analysis():
    # 1. Market data olish
    m15_df = get_gold_data(bars=M15_BARS)
    h1_df = get_gold_data(timeframe=mt5.TIMEFRAME_H1, bars=H1_BARS)

    if m15_df is None or h1_df is None:
        return None

    # Session filter
    session_status = get_session_status()
    session_ok = is_good_session()

    if not session_ok:
        print(f"[SESSION] {session_status} — Signal berilmaydi")

        return {
            "m15_df": m15_df,
            "symbol": SYMBOL,
            "m15_timeframe_name": M15_TIMEFRAME_NAME,
            "h1_timeframe_name": H1_TIMEFRAME_NAME,
            "h1_trend": "N/A",
            "m15_trend": "N/A",
            "d1_trend": "NEUTRAL",
            "d1_alignment_ok": True,
            "dxy_status": "UNKNOWN",
            "is_news_time": False,
            "news_reason": "Session blokladi",
            "alignment_text": "Session sabab alignment tekshirilmadi",
            "last_rsi": 0.0,
            "rsi_text": "N/A",
            "macd_text": "N/A",
            "candle_confirmation": "N/A",
            "support": 0.0,
            "resistance": 0.0,
            "atr_value": 0.0,
            "price_location": "N/A",
            "entry_zone_text": "N/A",
            "summary": f"{session_status} sababli signal tekshirilmadi",
            "setup_status": "NO TRADE",
            "trade_comment": "Sessiya yaroqsiz",
            "signal_strength": "WEAK",
            "trade_plan": "Sessiya yaroqsiz — kutish kerak",
            "final_signal": "WAIT",
            "alert_message": "ALERT: Sessiya yaroqsiz",
            "reason": f"WAIT: {session_status}",
            "suggested_entry": None,
            "suggested_sl": None,
            "suggested_tp": None,
            "risk_reward_ratio": None,
            "signal_mode": SIGNAL_MODE,
            "volume_status": "N/A",
            "session_status": session_status,
            "session_ok": session_ok,
            "stoch_rsi_text": "N/A",
            "divergence_text": "N/A",
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "trailing_sl": None,
            "breakeven_sl": None,
            "breakeven_active": False,
            "market_structure": "N/A",
            "order_block": "N/A",
            "liquidity_zones": "N/A",
            "fvg_data": {
                "type": "No FVG",
                "top": None,
                "bottom": None,
                "size": 0.0,
                "text": "FVG: Topilmadi",
                "in_zone": False,
            },
            "fvg_text": "FVG: Topilmadi",
            "breaker_block": "N/A",
            "imbalance_fill": "N/A",
            "wyckoff_phase": "N/A",
            "confluence": {
                "score": 0,
                "grade": "NO TRADE",
                "emoji": "❌",
                "details": [],
                "text": "CONFLUENCE: 0/20 — NO TRADE ❌",
            },
            "confluence_score": 0,
            "confluence_text": "CONFLUENCE: 0/20 — NO TRADE ❌",
            "ml_approved": True,
            "ml_probability": 0.0,
            "ml_reason": "ML tekshirilmadi — session blokladi",
        }

    # 2. Indikatorlarni hisoblash
    m15_df = add_ema(m15_df, [EMA_FAST, EMA_SLOW])
    m15_df = add_rsi(m15_df, RSI_PERIOD)
    m15_df = add_macd(m15_df)
    m15_df = add_atr(m15_df, ATR_PERIOD)
    m15_df = add_stochastic_rsi(m15_df)

    h1_df = add_ema(h1_df, [EMA_FAST, EMA_SLOW])

    # 3. Trend va alignment
    m15_trend = detect_trend(m15_df, EMA_FAST, EMA_SLOW)
    h1_trend = detect_trend(h1_df, EMA_FAST, EMA_SLOW)
    alignment_text = "3TF alignment hali hisoblanmadi"

    # 4. Asosiy qiymatlar
    current_price = m15_df["close"].iloc[-1]
    last_rsi = m15_df["RSI"].iloc[-1]
    rsi_text = interpret_rsi(last_rsi)
    macd_text = interpret_macd(m15_df)
    candle_confirmation = detect_candle_confirmation(m15_df)

    # Faza 2: Yangi tahlillar
    volume_status = analyze_volume(m15_df)
    session_status = get_session_status()
    session_ok = is_good_session()
    stoch_rsi_text = interpret_stochastic_rsi(m15_df)
    divergence_text = detect_rsi_divergence(m15_df)

    # Faza 4: Market structure — confluence dan OLDIN hisoblanishi kerak
    market_structure = check_market_structure(m15_df)
    order_block = detect_order_block(m15_df, m15_trend)
    liquidity_zones = detect_liquidity_zones(m15_df)

    # Faza C: ICT va Smart Money
    fvg_data = detect_fair_value_gap_advanced(m15_df)
    breaker_block = detect_breaker_block(m15_df, m15_trend)
    imbalance_fill = detect_imbalance_fill(m15_df)
    wyckoff_phase = detect_wyckoff_phase(m15_df)

    confluence = calculate_confluence_score(
        h1_trend=h1_trend,
        m15_trend=m15_trend,
        rsi_text=rsi_text,
        macd_text=macd_text,
        candle=candle_confirmation,
        fvg=fvg_data,
        wyckoff=wyckoff_phase,
        market_struct=market_structure,
        session=session_status,
        volume=volume_status,
        divergence=divergence_text,
    )

    support, resistance = find_support_resistance(m15_df)
    price_location = detect_price_location(current_price, support, resistance)
    ema20_value = m15_df[f"EMA_{EMA_FAST}"].iloc[-1]
    atr_value = m15_df["ATR"].iloc[-1]

    # 5. Entry zone
    entry_zone_text = detect_entry_zone(
        m15_df,
        m15_trend,
        current_price,
        ema20_value,
        support,
        resistance,
        atr_value,
    )

    # 6. Yagona signal core
    signal_pkg = build_signal_package(
        h1_trend=h1_trend,
        m15_trend=m15_trend,
        last_rsi=last_rsi,
        rsi_text=rsi_text,
        macd_text=macd_text,
        current_price=current_price,
        support=support,
        resistance=resistance,
        price_location=price_location,
        entry_zone_text=entry_zone_text,
        candle_confirmation=candle_confirmation,
        atr_value=atr_value,
        ema20_value=ema20_value,
        confluence_score=confluence["score"],
        min_risk_reward=MIN_RISK_REWARD,
        confluence_min_score=0,
    )

    setup_status = signal_pkg["setup_status"]
    trade_comment = signal_pkg["trade_comment"]
    signal_strength = signal_pkg["signal_strength"]
    trade_plan = signal_pkg["trade_plan"]
    summary = signal_pkg["summary"]
    suggested_entry = signal_pkg["suggested_entry"]
    suggested_sl = signal_pkg["suggested_sl"]
    suggested_tp = signal_pkg["suggested_tp"]
    risk_reward_ratio = signal_pkg["risk_reward_ratio"]
    tp1 = signal_pkg["tp1"]
    tp2 = signal_pkg["tp2"]
    tp3 = signal_pkg["tp3"]
    trailing_sl = signal_pkg["trailing_sl"]
    breakeven_sl = signal_pkg["breakeven_sl"]
    breakeven_active = signal_pkg["breakeven_active"]
    final_signal = signal_pkg["final_signal"]
    reason = signal_pkg["reason"]
    alert_message = signal_pkg["alert_message"]

    d1_trend = "NEUTRAL"
    d1_alignment_ok = True
    alignment_text = "Agressiv rejim: D1 filtrsiz"

    dxy_status = get_dxy_status()
    is_news_time, news_reason = check_high_impact_news()

    # ML Filter o'chirildi (Agressiv rejim)
    ml_approved = True
    ml_reason = "ML skip"
    ml_probability = 0.0

    alert_message = generate_alert_message(final_signal, setup_status, signal_strength)

    # 16. Yakuniy natija
    return {
        "m15_df": m15_df,
        "symbol": SYMBOL,
        "m15_timeframe_name": M15_TIMEFRAME_NAME,
        "h1_timeframe_name": H1_TIMEFRAME_NAME,
        "h1_trend": h1_trend,
        "m15_trend": m15_trend,
        "d1_trend": d1_trend,
        "d1_alignment_ok": d1_alignment_ok,
        "dxy_status": dxy_status,
        "is_news_time": is_news_time,
        "news_reason": news_reason,
        "alignment_text": alignment_text,
        "last_rsi": last_rsi,
        "rsi_text": rsi_text,
        "macd_text": macd_text,
        "candle_confirmation": candle_confirmation,
        "support": support,
        "resistance": resistance,
        "atr_value": atr_value,
        "price_location": price_location,
        "entry_zone_text": entry_zone_text,
        "summary": summary,
        "setup_status": setup_status,
        "trade_comment": trade_comment,
        "signal_strength": signal_strength,
        "trade_plan": trade_plan,
        "final_signal": final_signal,
        "alert_message": alert_message,
        "reason": reason,
        "suggested_entry": suggested_entry,
        "suggested_sl": suggested_sl,
        "suggested_tp": suggested_tp,
        "risk_reward_ratio": risk_reward_ratio,
        "signal_mode": SIGNAL_MODE,
        "volume_status": volume_status,
        "session_status": session_status,
        "session_ok": session_ok,
        "stoch_rsi_text": stoch_rsi_text,
        "divergence_text": divergence_text,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "trailing_sl": trailing_sl,
        "breakeven_sl": breakeven_sl,
        "breakeven_active": breakeven_active,
        "market_structure": market_structure,
        "order_block": order_block,
        "liquidity_zones": liquidity_zones,
        "fvg_data": fvg_data,
        "fvg_text": fvg_data["text"],
        "breaker_block": breaker_block,
        "imbalance_fill": imbalance_fill,
        "wyckoff_phase": wyckoff_phase,
        "confluence": confluence,
        "confluence_score": confluence["score"],
        "confluence_text": confluence["text"],
        "ml_approved": ml_approved,
        "ml_probability": ml_probability,
        "ml_reason": ml_reason,
    }