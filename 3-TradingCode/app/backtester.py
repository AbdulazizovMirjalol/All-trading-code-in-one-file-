"""
backtester.py — Signal sifatini o'tgan ma'lumotlarda tekshirish.

Ishlash tartibi:
  1. MT5 dan oxirgi N ta sham oladi
  2. Har bir shamda signal logikasini ishlatadi
  3. Signal BUY/SELL bo'lsa, keyingi shamlarda natijani tekshiradi
  4. TP1/TP2/TP3 yoki SL ga yetganini aniqlaydi
  5. Winrate va boshqa statistikani chiqaradi
"""
from signal_engine import build_signal_package, apply_three_tf_alignment
from market_regime import detect_market_regime
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json
from pathlib import Path

from config import (
    SYMBOL,
    EMA_FAST,
    EMA_SLOW,
    RSI_PERIOD,
    ATR_PERIOD,
    DXY_SYMBOL_CANDIDATES,
    ENABLE_DXY_FILTER,
    BACKTEST_SPREAD_PIPS,
    BACKTEST_SLIPPAGE_PIPS,
)

from indicators import (
    add_ema,
    add_rsi,
    add_macd,
    add_atr,
    add_stochastic_rsi,
    detect_trend,
    interpret_rsi,
    interpret_macd,
    detect_candle_confirmation,
    find_support_resistance,
    detect_price_location,
    detect_entry_zone,
    detect_setup_status,
    detect_signal_strength,
    generate_final_signal,
    generate_entry_price,
    generate_risk_levels,
    calculate_risk_reward,
    calculate_multi_tp,
    analyze_volume,
    detect_rsi_divergence,
    check_market_structure,
    detect_order_block,
    detect_liquidity_zones,
    detect_fair_value_gap_advanced,
    detect_breaker_block,
    detect_imbalance_fill,
    detect_wyckoff_phase,
    calculate_confluence_score,
)

def get_backtest_session_status(candle_time) -> str:
    """
    Backtest uchun sham vaqtiga qarab session aniqlaydi.
    candle_time UTC deb olinadi, UZ (UTC+5) ga o'tkaziladi.
    """
    hour = candle_time.hour + 5
    if hour >= 24:
        hour -= 24

    if 17 <= hour <= 20:
        return "OVERLAP: London + NY (Eng kuchli sessiya)"
    elif 12 <= hour < 17:
        return "LONDON: Kuchli sessiya"
    elif 20 < hour <= 23:
        return "NEW YORK: Kuchli sessiya"
    elif 3 <= hour < 12:
        return "ASIA: Zaif sessiya — signal ishonchsiz"
    else:
        return "CLOSED: Bozor faol emas"
    
def get_backtest_d1_trend(df_m15: pd.DataFrame, current_time) -> str:
    """
    M15 tarixiy datadan taxminiy D1 trend olish.
    Oxirgi 96 ta M15 = 1 kun deb olinadi.
    """
    history = df_m15[df_m15["time"] <= current_time].copy()

    if len(history) < 96 * 20:
        return "NEUTRAL"

    history = history.set_index("time")
    d1 = history[["open", "high", "low", "close"]].resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna().reset_index()

    if len(d1) < 20:
        return "NEUTRAL"

    d1["EMA_20"] = d1["close"].ewm(span=20, adjust=False).mean()
    d1["EMA_50"] = d1["close"].ewm(span=50, adjust=False).mean()

    close = d1["close"].iloc[-1]
    ema20 = d1["EMA_20"].iloc[-1]
    ema50 = d1["EMA_50"].iloc[-1]

    if close > ema20 > ema50:
        return "BULLISH"
    elif close < ema20 < ema50:
        return "BEARISH"
    return "NEUTRAL"

def get_backtest_dxy_symbol():
    """
    Brokerda mavjud DXY symbolni topadi.
    """
    if not ENABLE_DXY_FILTER:
        return None

    for candidate in DXY_SYMBOL_CANDIDATES:
        info = mt5.symbol_info(candidate)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(candidate, True)
            return candidate

    return None


def get_backtest_dxy_data(bars: int = 4000) -> pd.DataFrame:
    """
    Backtest uchun tarixiy DXY M15 ma'lumotini oladi.
    """
    selected_symbol = get_backtest_dxy_symbol()
    if selected_symbol is None:
        return pd.DataFrame()

    rates = mt5.copy_rates_from_pos(selected_symbol, mt5.TIMEFRAME_M15, 0, bars)
    if rates is None or len(rates) < 30:
        return pd.DataFrame()

    df_dxy = pd.DataFrame(rates)
    df_dxy["time"] = pd.to_datetime(df_dxy["time"], unit="s")
    df_dxy = df_dxy.sort_values("time").reset_index(drop=True)
    return df_dxy


def get_backtest_dxy_status(df_dxy: pd.DataFrame, current_time) -> str:
    """
    Tarixiy sham vaqtigacha bo'lgan DXY ma'lumotidan
    EMA10 vs EMA20 orqali status chiqaradi.
    Live logikaga maksimal yaqin parity.
    """
    if not ENABLE_DXY_FILTER:
        return "UNKNOWN"

    if df_dxy is None or df_dxy.empty:
        return "UNKNOWN"

    history = df_dxy[df_dxy["time"] <= current_time].tail(30).copy()
    if len(history) < 20:
        return "UNKNOWN"

    history["EMA_10"] = history["close"].ewm(span=10, adjust=False).mean()
    history["EMA_20"] = history["close"].ewm(span=20, adjust=False).mean()

    ema10 = history["EMA_10"].iloc[-1]
    ema20 = history["EMA_20"].iloc[-1]

    if ema10 > ema20:
        return "STRENGTHENING"
    elif ema10 < ema20:
        return "WEAKENING"
    return "FLAT"

NEWS_HISTORY_PATH = Path("data/news_history.json")


def load_news_history():
    """
    Backtest uchun tarixiy news faylini yuklaydi.
    Format:
    [
      {"time": "2026-03-18 15:30", "impact": "high", "title": "..."},
      ...
    ]
    """
    if not NEWS_HISTORY_PATH.exists():
        return []

    try:
        raw = json.loads(NEWS_HISTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []

        parsed = []
        for item in raw:
            if not isinstance(item, dict):
                continue

            news_time_str = str(item.get("time", "")).strip()
            impact = str(item.get("impact", "")).strip().lower()
            title = str(item.get("title", "")).strip()

            if not news_time_str:
                continue

            try:
                news_time = pd.to_datetime(news_time_str)
            except Exception:
                continue

            parsed.append({
                "time": news_time,
                "impact": impact,
                "title": title,
            })

        return parsed

    except Exception:
        return []


def check_backtest_high_impact_news(news_history, current_time, window_minutes: int = 30):
    """
    current_time atrofida high impact news bo'lsa block qaytaradi.
    Live parity uchun soddalashtirilgan tarixiy news filter.
    """
    if not news_history:
        return False, "No historical news file"

    current_time = pd.to_datetime(current_time)
    window_before = current_time - timedelta(minutes=window_minutes)
    window_after = current_time + timedelta(minutes=window_minutes)

    for item in news_history:
        if item["impact"] != "high":
            continue

        if window_before <= item["time"] <= window_after:
            reason = f"High impact news window: {item['title']}"
            return True, reason

    return False, ""


def connect():
    if not mt5.initialize():
        print(f"MT5 ulanmadi: {mt5.last_error()}")
        return False
    return True


def disconnect():
    mt5.shutdown()


def get_data(bars: int = 2000) -> pd.DataFrame:
    """Ko'proq tarixiy ma'lumot olish — backtesting uchun."""
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    if rates is None or len(rates) == 0:
        print("Ma'lumot olinmadi!")
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def prepare_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Barcha indikatorlarni hisoblash."""
    df = add_ema(df, [EMA_FAST, EMA_SLOW])
    df = add_rsi(df, RSI_PERIOD)
    df = add_macd(df)
    df = add_atr(df, ATR_PERIOD)
    df = add_stochastic_rsi(df)
    return df


def check_trade_result(
    df: pd.DataFrame,
    signal: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    start_idx: int,
    max_bars: int = 100,
) -> dict:
    """
    Signal chiqqandan keyin natijani tekshirish.

    Keyingi max_bars ta sham ichida:
      TP1/TP2/TP3 ga yetsa — WIN
      SL ga yetsa  — LOSS
      Hech biri bo'lmasa — TIMEOUT (WAIT)
    """
    result = {
        "outcome":   "TIMEOUT",
        "bars_held": 0,
        "tp_hit":    0,      # Qaysi TP ga yetdi (1, 2, 3)
        "pnl_pips":  0.0,    # Foyda/zarar pip da
    }

    trade_cost = BACKTEST_SPREAD_PIPS + BACKTEST_SLIPPAGE_PIPS

    for i in range(start_idx, min(start_idx + max_bars, len(df))):
        row  = df.iloc[i]
        high = row["high"]
        low  = row["low"]
        result["bars_held"] = i - start_idx + 1

        if signal == "BUY":

            hit_sl = low <= sl
            hit_tp1 = bool(tp1 and high >= tp1)
            hit_tp2 = bool(tp2 and high >= tp2)
            hit_tp3 = bool(tp3 and high >= tp3)

            # Bir sham ichida SL va TP birga tegsa, konservativ ravishda LOSS deb olamiz.
            if hit_sl and (hit_tp1 or hit_tp2 or hit_tp3):
                result["outcome"] = "LOSS"
                result["tp_hit"] = 0
                result["pnl_pips"] = round((sl - entry) - trade_cost, 2)
                break
            if hit_sl:
                result["outcome"]  = "LOSS"
                result["pnl_pips"] = round((sl - entry) - trade_cost, 2)
                break
            if hit_tp3:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 3
                result["pnl_pips"] = round((tp3 - entry) - trade_cost, 2)
                break
            if hit_tp2:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 2
                result["pnl_pips"] = round(tp2 - entry, 2)
                break
            if hit_tp1:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 1
                result["pnl_pips"] = round(tp1 - entry, 2)
                break

        elif signal == "SELL":
            hit_sl = high >= sl
            hit_tp1 = bool(tp1 and low <= tp1)
            hit_tp2 = bool(tp2 and low <= tp2)
            hit_tp3 = bool(tp3 and low <= tp3)

            # Bir sham ichida SL va TP birga tegsa, konservativ ravishda LOSS deb olamiz.
            if hit_sl and (hit_tp1 or hit_tp2 or hit_tp3):
                result["outcome"] = "LOSS"
                result["tp_hit"] = 0
                result["pnl_pips"] = round((entry - sl) - trade_cost, 2)
                break

            if hit_sl:
                result["outcome"]  = "LOSS"
                result["pnl_pips"] = round((entry - sl) - trade_cost, 2)
                break
            if hit_tp3:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 3
                result["pnl_pips"] = round((entry - tp3) - trade_cost, 2)
                break
            if hit_tp2:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 2
                result["pnl_pips"] = round((entry - tp2) - trade_cost, 2)
                break
            if hit_tp1:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 1
                result["pnl_pips"] = round((entry - tp1) - trade_cost, 2)
                break

    return result


def run_backtest(bars: int = 2000, warmup: int = 100) -> pd.DataFrame:
    """
    Asosiy backtest funksiyasi.

    bars   = nechta M15 sham tekshiriladi (2000 = ~20 kun)
    warmup = dastlabki N ta sham indikator isishi uchun o'tkazib yuboriladi
    """
    print(f"\n{'='*55}")
    print(f"  BACKTESTING BOSHLANMOQDA")
    print(f"  Symbol : {SYMBOL}  |  Timeframe: M15")
    print(f"  Shamlar: {bars}   |  Warmup: {warmup}")
    print(f"{'='*55}\n")

    if not connect():
        return pd.DataFrame()

    df = get_data(bars)
    if df.empty:
        disconnect()
        return pd.DataFrame()
    
    # H1 data ham olish
    # M15 dan H1 ga nisbat: 4 ta M15 = 1 ta H1.
    # Shuning uchun bars katta bo'lsa, H1 bars ham avtomatik ko'payadi.
    h1_bars = max(int(bars / 4) + 300, 500)

    h1_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, h1_bars)

    if h1_rates is None or len(h1_rates) < 100:
        print("H1 data yetarli emas!")
        disconnect()
        return pd.DataFrame()

    df_h1 = pd.DataFrame(h1_rates)
    df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s")
    df_h1 = df_h1.sort_values("time").reset_index(drop=True)
    df_h1 = add_ema(df_h1, [EMA_FAST, EMA_SLOW])

    dxy_bars = max(bars + 300, 500)
    df_dxy = get_backtest_dxy_data(dxy_bars)
    news_history = load_news_history()

    df = prepare_indicators(df)
    df = df.dropna().reset_index(drop=True)

    trades = []
    diagnostic_rows = []
    skip_to = 0

    diagnostics = {
        "candles_checked": 0,
        "session_blocked": 0,
        "session_passed": 0,
        "h1_ready": 0,
        "setup_ready_buy": 0,
        "setup_ready_sell": 0,
        "setup_buy_watch": 0,
        "setup_sell_watch": 0,
        "setup_no_trade": 0,
        "rr_none": 0,
        "rr_below_min": 0,
        "confluence_blocked": 0,
        "three_tf_blocked": 0,
        "dxy_blocked": 0,
        "news_blocked": 0,
        "final_buy": 0,
        "final_sell": 0,
    }

    for idx in range(warmup, len(df) - 60):
        # Avvalgi signal hali tugamagan bo'lsa o'tkazib yuboramiz
        if idx < skip_to:
            continue

        # Oyna — oxirgi 100 ta sham signal hisoblash uchun
        window = df.iloc[max(0, idx-100): idx+1].copy()
        if len(window) < 50:
            continue

        current = window.iloc[-1]
        diagnostics["candles_checked"] += 1

        # Indikatorlar
        m15_trend = detect_trend(window, EMA_FAST, EMA_SLOW)
        # H1 trend
        h1_window = df_h1[df_h1["time"] <= current["time"]].tail(50)
        if len(h1_window) < 10:
            continue
        h1_trend = detect_trend(h1_window, EMA_FAST, EMA_SLOW)
        diagnostics["h1_ready"] += 1

        d1_trend = get_backtest_d1_trend(df, current["time"])
        dxy_status = get_backtest_dxy_status(df_dxy, current["time"])
        is_news_time, news_reason = check_backtest_high_impact_news(
            news_history,
            current["time"],
            window_minutes=30,
        )

        historical_session = get_backtest_session_status(current["time"])
        if "ASIA" in historical_session or "CLOSED" in historical_session:
            diagnostics["session_blocked"] += 1
            continue

        diagnostics["session_passed"] += 1

        rsi_text  = interpret_rsi(current["RSI"])
        macd_text = interpret_macd(window)
        candle    = detect_candle_confirmation(window)

        try:
            support, resistance = find_support_resistance(window)
        except Exception:
            continue

        price_loc   = detect_price_location(
            current["close"], support, resistance
        )
        ema20       = current[f"EMA_{EMA_FAST}"]
        atr         = current["ATR"]
        entry_zone  = detect_entry_zone(
            window, m15_trend, current["close"],
            ema20, support, resistance, atr
        )


        volume_status = analyze_volume(window)
        session_status = get_backtest_session_status(current["time"])
        divergence_text = detect_rsi_divergence(window)
        market_structure = check_market_structure(window)
        order_block = detect_order_block(window, m15_trend)
        liquidity_zones = detect_liquidity_zones(window)
        fvg_data = detect_fair_value_gap_advanced(window)
        breaker_block = detect_breaker_block(window, m15_trend)
        imbalance_fill = detect_imbalance_fill(window)
        wyckoff_phase = detect_wyckoff_phase(window)

        confluence = calculate_confluence_score(
            h1_trend=h1_trend,
            m15_trend=m15_trend,
            rsi_text=rsi_text,
            macd_text=macd_text,
            candle=candle,
            fvg=fvg_data,
            wyckoff=wyckoff_phase,
            market_struct=market_structure,
            session=session_status,
            volume=volume_status,
            divergence=divergence_text,
        )

        regime_result = detect_market_regime(window)

        market_regime = regime_result.regime
        regime_direction = regime_result.trend_direction
        regime_strength = regime_result.trend_strength
        volatility_state = regime_result.volatility_state
        atr_percentile = regime_result.atr_percentile
        regime_reason = regime_result.reason

        signal_pkg = build_signal_package(
            h1_trend=h1_trend,
            m15_trend=m15_trend,
            last_rsi=current["RSI"],
            rsi_text=rsi_text,
            macd_text=macd_text,
            current_price=current["close"],
            support=support,
            resistance=resistance,
            price_location=price_loc,
            entry_zone_text=entry_zone,
            candle_confirmation=candle,
            atr_value=atr,
            ema20_value=ema20,
            market_regime=market_regime,
            confluence_score=confluence["score"],
            min_risk_reward=1.5,
            confluence_min_score=7,
        )

        setup = signal_pkg["setup_status"]

        if setup == "READY BUY":
            diagnostics["setup_ready_buy"] += 1
        elif setup == "READY SELL":
            diagnostics["setup_ready_sell"] += 1
        elif setup == "BUY WATCH":
            diagnostics["setup_buy_watch"] += 1
        elif setup == "SELL WATCH":
            diagnostics["setup_sell_watch"] += 1
        else:
            diagnostics["setup_no_trade"] += 1

        strength = signal_pkg["signal_strength"]
        entry_price = signal_pkg["suggested_entry"]
        sl = signal_pkg["suggested_sl"]
        tp = signal_pkg["suggested_tp"]
        rr = signal_pkg["risk_reward_ratio"]
        signal = signal_pkg["final_signal"]
        tp1 = signal_pkg["tp1"]
        tp2 = signal_pkg["tp2"]
        tp3 = signal_pkg["tp3"]

        block_reason = signal_pkg.get("block_reason", "")
        reason = signal_pkg.get("reason", "")

        quality_score = signal_pkg.get("quality_score", "")
        quality_grade = signal_pkg.get("quality_grade", "")
        quality_text = signal_pkg.get("quality_text", "")
        buy_score = signal_pkg.get("buy_score", "")
        sell_score = signal_pkg.get("sell_score", "")
        conflict_score = signal_pkg.get("conflict_score", "")
        net_bias = signal_pkg.get("net_bias", "")
        entry_quality_score = signal_pkg.get("entry_quality_score", "")
        entry_quality_grade = signal_pkg.get("entry_quality_grade", "")

        enable_market_regime_filter = signal_pkg.get("enable_market_regime_filter", "")
        enable_trend_direction_filter = signal_pkg.get("enable_trend_direction_filter", "")
        enable_quality_score_filter = signal_pkg.get("enable_quality_score_filter", "")
        enable_conflict_score_filter = signal_pkg.get("enable_conflict_score_filter", "")
        enable_entry_quality_filter = signal_pkg.get("enable_entry_quality_filter", "")
        min_quality_score = signal_pkg.get("min_quality_score", "")
        max_conflict_score = signal_pkg.get("max_conflict_score", "")
        min_entry_quality_score = signal_pkg.get("min_entry_quality_score", "")

        raw_engine_signal = signal
        final_block_reason = block_reason
        final_reason = reason

        if rr is None:
            diagnostics["rr_none"] += 1
        elif rr < 1.5:
            diagnostics["rr_below_min"] += 1

        if signal == "WAIT" and "Confluence score past" in signal_pkg["reason"]:
            diagnostics["confluence_blocked"] += 1


        raw_signal_before_3tf = signal

        signal, three_tf_alignment_ok, alignment_text_bt, _ = apply_three_tf_alignment(
            final_signal=signal,
            d1_trend=d1_trend,
            h1_trend=h1_trend,
            m15_trend=m15_trend,
            reason="",
        )

        if raw_signal_before_3tf in ["BUY", "SELL"] and signal == "WAIT":
            diagnostics["three_tf_blocked"] += 1
            final_block_reason = "THREE_TF_ALIGNMENT"
            final_reason = "WAIT: 3TF alignment mos emas."

        if signal == "BUY" and dxy_status == "STRENGTHENING":
            diagnostics["dxy_blocked"] += 1
            signal = "WAIT"
            final_block_reason = "DXY_FILTER"
            final_reason = "WAIT: BUY signal DXY strengthening holatida bloklandi."

        elif signal == "SELL" and dxy_status == "WEAKENING":
            diagnostics["dxy_blocked"] += 1
            signal = "WAIT"
            final_block_reason = "DXY_FILTER"
            final_reason = "WAIT: SELL signal DXY weakening holatida bloklandi."

        if signal in ["BUY", "SELL"] and is_news_time:
            diagnostics["news_blocked"] += 1
            signal = "WAIT"
            final_block_reason = "NEWS_FILTER"
            final_reason = f"WAIT: High impact news bloklandi. {news_reason}"

        diagnostic_rows.append({
            "time": current["time"],
            "raw_engine_signal": raw_engine_signal,
            "final_signal_after_filters": signal,
            "setup": setup,
            "strength": strength,
            "block_reason": final_block_reason,
            "reason": final_reason,

            "entry": entry_price,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr": rr,

            "quality_score": quality_score,
            "quality_grade": quality_grade,
            "quality_text": quality_text,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "conflict_score": conflict_score,
            "net_bias": net_bias,
            "entry_quality_score": entry_quality_score,
            "entry_quality_grade": entry_quality_grade,

            "enable_market_regime_filter": enable_market_regime_filter,
            "enable_trend_direction_filter": enable_trend_direction_filter,
            "enable_quality_score_filter": enable_quality_score_filter,
            "enable_conflict_score_filter": enable_conflict_score_filter,
            "enable_entry_quality_filter": enable_entry_quality_filter,
            "min_quality_score": min_quality_score,
            "max_conflict_score": max_conflict_score,
            "min_entry_quality_score": min_entry_quality_score,

            "market_regime": market_regime,
            "regime_direction": regime_direction,
            "regime_strength": regime_strength,
            "volatility_state": volatility_state,
            "atr_percentile": atr_percentile,
            "regime_reason": regime_reason,

            "h1_trend": h1_trend,
            "m15_trend": m15_trend,
            "d1_trend": d1_trend,
            "alignment_text": alignment_text_bt,
            "dxy_status": dxy_status,
            "news_blocked": is_news_time,
            "news_reason": news_reason,

            "rsi": current["RSI"],
            "atr": atr,
            "rsi_text": rsi_text,
            "macd_text": macd_text,
            "session_status": session_status,
            "volume_status": volume_status,
            "divergence_text": divergence_text,
            "market_structure": market_structure,
            "order_block": order_block,
            "liquidity_zones": liquidity_zones,
            "fvg_text": fvg_data["text"],
            "wyckoff_phase": wyckoff_phase,
            "confluence_score": confluence["score"],
            "confluence_text": confluence["text"],
        })

        if signal not in ["BUY", "SELL"]:
            continue

        if signal == "BUY":
            diagnostics["final_buy"] += 1
        elif signal == "SELL":
            diagnostics["final_sell"] += 1

        # Natijani tekshirish
        trade_result = check_trade_result(
            df, signal, entry_price, sl, tp1, tp2, tp3,
            start_idx=idx + 1,
        )

        risk_pips = abs(entry_price - sl) if entry_price is not None and sl is not None else 0

        if risk_pips > 0:
            r_multiple = trade_result["pnl_pips"] / risk_pips
        else:
            r_multiple = 0

        trades.append({
            "time":      current["time"],
            "signal":    signal,
            "setup":     setup,
            "strength":  strength,
            "entry":     entry_price,
            "sl":        sl,
            "tp1":       tp1,
            "tp2":       tp2,
            "tp3":       tp3,
            "rr":        rr,
            "risk_pips": risk_pips,
            "r_multiple": r_multiple,
            "block_reason": block_reason,
            "reason": reason,

            "quality_score": quality_score,
            "quality_grade": quality_grade,
            "quality_text": quality_text,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "conflict_score": conflict_score,
            "net_bias": net_bias,
            "entry_quality_score": entry_quality_score,
            "entry_quality_grade": entry_quality_grade,

            "market_regime": market_regime,
            "regime_direction": regime_direction,
            "regime_strength": regime_strength,
            "volatility_state": volatility_state,
            "atr_percentile": atr_percentile,
            "regime_reason": regime_reason,

            "entry_zone": entry_zone,
            "candle_confirmation": candle,
            "price_location": price_loc,
            "outcome":   trade_result["outcome"],
            "tp_hit":    trade_result["tp_hit"],
            "bars_held": trade_result["bars_held"],
            "pnl_pips":  trade_result["pnl_pips"],
            "rsi":        current["RSI"],
            "atr":        atr,
            "h1_trend":   h1_trend,
            "m15_trend":  m15_trend,
            "d1_trend":   d1_trend,
            "alignment_text": alignment_text_bt,
            "dxy_status": dxy_status,
            "news_blocked": is_news_time,
            "news_reason": news_reason,
            "rsi_text":   rsi_text,
            "macd_text":  macd_text,
            "volume_status": volume_status,
            "session_status": session_status,
            "divergence_text": divergence_text,
            "market_structure": market_structure,
            "order_block": order_block,
            "liquidity_zones": liquidity_zones,
            "fvg_text":    fvg_data["text"],
            "wyckoff_phase": wyckoff_phase,
            "confluence_score": confluence["score"],
            "confluence_text": confluence["text"],
        })

        # Keyingi signalni oldingi signal tugaguncha o'tkazib yuboramiz
        skip_to = idx + trade_result["bars_held"] + 1

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    diagnostics_df = pd.DataFrame(diagnostic_rows) if diagnostic_rows else pd.DataFrame()

    if not diagnostics_df.empty:
        diagnostics_path = logs_dir / f"backtest_diagnostics_{timestamp}.csv"
        diagnostics_df.to_csv(diagnostics_path, index=False)
        print(f"\n  Backtest diagnostics saqlandi: {diagnostics_path}")
        print_diagnostics_report(diagnostics_df)
    disconnect()

    print(f"\n{'='*55}")
    print(f"  BACKTEST DIAGNOSTIKASI")
    print(f"{'='*55}")
    print(f"  Tekshirilgan shamlar : {diagnostics['candles_checked']}")
    print(f"  Session bloklandi    : {diagnostics['session_blocked']}")
    print(f"  Session o'tdi        : {diagnostics['session_passed']}")
    print(f"  H1 ready             : {diagnostics['h1_ready']}")
    print(f"  READY BUY            : {diagnostics['setup_ready_buy']}")
    print(f"  READY SELL           : {diagnostics['setup_ready_sell']}")
    print(f"  BUY WATCH            : {diagnostics['setup_buy_watch']}")
    print(f"  SELL WATCH           : {diagnostics['setup_sell_watch']}")
    print(f"  NO TRADE             : {diagnostics['setup_no_trade']}")
    print(f"  RR None              : {diagnostics['rr_none']}")
    print(f"  RR < 1.5             : {diagnostics['rr_below_min']}")
    print(f"  Confluence blocked   : {diagnostics['confluence_blocked']}")
    print(f"  3TF blocked          : {diagnostics['three_tf_blocked']}")
    print(f"  DXY blocked          : {diagnostics['dxy_blocked']}")
    print(f"  News blocked         : {diagnostics['news_blocked']}")
    print(f"  Final BUY            : {diagnostics['final_buy']}")
    print(f"  Final SELL           : {diagnostics['final_sell']}")
    print(f"{'='*55}\n")

    trades_df = pd.DataFrame(trades)

    if trades_df.empty:
        print("Hech qanday signal topilmadi!")
        print_tuning_recommendations(diagnostics_df, trades_df)
        return trades_df

    print_tuning_recommendations(diagnostics_df, trades_df)
    return trades_df

def print_diagnostics_report(diagnostics_df: pd.DataFrame):
    """
    Backtest diagnostics natijalarini terminalga chiqaradi.
    Bu BUY/SELL bo'lmagan WAIT holatlarni ham tahlil qiladi.
    """
    if diagnostics_df is None or diagnostics_df.empty:
        print("\nBacktest diagnostics bo'sh.\n")
        return

    total = len(diagnostics_df)

    print(f"\n{'='*55}")
    print("  BACKTEST DIAGNOSTICS REPORT")
    print(f"{'='*55}")
    print(f"  Jami diagnostic yozuvlar: {total}")

    if "raw_engine_signal" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  Raw engine signal:")
        print(
            diagnostics_df["raw_engine_signal"]
            .fillna("N/A")
            .value_counts()
            .to_string()
        )

    if "final_signal_after_filters" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  Final signal after filters:")
        print(
            diagnostics_df["final_signal_after_filters"]
            .fillna("N/A")
            .value_counts()
            .to_string()
        )

    if "block_reason" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  Block reason:")
        print(
            diagnostics_df["block_reason"]
            .fillna("NOT_BLOCKED")
            .replace("", "NOT_BLOCKED")
            .value_counts()
            .to_string()
        )

    if "market_regime" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  Market regime:")
        print(
            diagnostics_df["market_regime"]
            .fillna("N/A")
            .value_counts()
            .to_string()
        )

    if "volatility_state" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  Volatility state:")
        print(
            diagnostics_df["volatility_state"]
            .fillna("N/A")
            .value_counts()
            .to_string()
        )

    if "quality_score" in diagnostics_df.columns:
        q = pd.to_numeric(diagnostics_df["quality_score"], errors="coerce").dropna()
        if not q.empty:
            print(f"{'─'*55}")
            print(f"  Avg quality score : {q.mean():.2f}")
            print(f"  Min quality score : {q.min():.2f}")
            print(f"  Max quality score : {q.max():.2f}")

    if "entry_quality_score" in diagnostics_df.columns:
        eq = pd.to_numeric(
            diagnostics_df["entry_quality_score"], errors="coerce"
        ).dropna()
        if not eq.empty:
            print(f"{'─'*55}")
            print(f"  Avg entry quality : {eq.mean():.2f}")
            print(f"  Min entry quality : {eq.min():.2f}")
            print(f"  Max entry quality : {eq.max():.2f}")

    if "conflict_score" in diagnostics_df.columns:
        cf = pd.to_numeric(
            diagnostics_df["conflict_score"], errors="coerce"
        ).dropna()
        if not cf.empty:
            print(f"{'─'*55}")
            print(f"  Avg conflict score: {cf.mean():.2f}")
            print(f"  Max conflict score: {cf.max():.2f}")
            print(f"  Conflict >= 35    : {len(cf[cf >= 35])}")

    if "setup" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  Setup status:")
        print(
            diagnostics_df["setup"]
            .fillna("N/A")
            .value_counts()
            .to_string()
        )

    # ---------------------------------------------------------
    # GROUP DIAGNOSTICS: BLOCK REASON QUALITY
    # ---------------------------------------------------------
    if "block_reason" in diagnostics_df.columns and "quality_score" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  AVG QUALITY BY BLOCK REASON:")

        temp_df = diagnostics_df.copy()
        temp_df["block_reason"] = (
            temp_df["block_reason"]
            .fillna("NOT_BLOCKED")
            .replace("", "NOT_BLOCKED")
        )
        temp_df["quality_score"] = pd.to_numeric(
            temp_df["quality_score"],
            errors="coerce",
        )

        grouped = temp_df.groupby("block_reason")["quality_score"].agg(
            ["count", "mean", "min", "max"]
        )

        if grouped.empty:
            print("  Ma'lumot yo‘q.")
        else:
            print(grouped.round(2).to_string())

    # ---------------------------------------------------------
    # GROUP DIAGNOSTICS: MARKET REGIME VS FINAL SIGNAL
    # ---------------------------------------------------------
    if (
        "market_regime" in diagnostics_df.columns
        and "final_signal_after_filters" in diagnostics_df.columns
    ):
        print(f"{'─'*55}")
        print("  MARKET REGIME VS FINAL SIGNAL:")

        table = pd.crosstab(
            diagnostics_df["market_regime"].fillna("N/A"),
            diagnostics_df["final_signal_after_filters"].fillna("N/A"),
        )

        if table.empty:
            print("  Ma'lumot yo‘q.")
        else:
            print(table.to_string())

    # ---------------------------------------------------------
    # GROUP DIAGNOSTICS: QUALITY GRADE VS FINAL SIGNAL
    # ---------------------------------------------------------
    if (
        "quality_grade" in diagnostics_df.columns
        and "final_signal_after_filters" in diagnostics_df.columns
    ):
        print(f"{'─'*55}")
        print("  QUALITY GRADE VS FINAL SIGNAL:")

        table = pd.crosstab(
            diagnostics_df["quality_grade"].fillna("N/A"),
            diagnostics_df["final_signal_after_filters"].fillna("N/A"),
        )

        if table.empty:
            print("  Ma'lumot yo‘q.")
        else:
            print(table.to_string())

    # ---------------------------------------------------------
    # GROUP DIAGNOSTICS: SETUP VS BLOCK REASON
    # ---------------------------------------------------------
    if "setup" in diagnostics_df.columns and "block_reason" in diagnostics_df.columns:
        print(f"{'─'*55}")
        print("  SETUP VS BLOCK REASON:")

        temp_df = diagnostics_df.copy()
        temp_df["block_reason"] = (
            temp_df["block_reason"]
            .fillna("NOT_BLOCKED")
            .replace("", "NOT_BLOCKED")
        )

        table = pd.crosstab(
            temp_df["setup"].fillna("N/A"),
            temp_df["block_reason"].fillna("N/A"),
        )

        if table.empty:
            print("  Ma'lumot yo‘q.")
        else:
            print(table.to_string())

    # ---------------------------------------------------------
    # GROUP DIAGNOSTICS: ENTRY GRADE VS FINAL SIGNAL
    # ---------------------------------------------------------
    if (
        "entry_quality_grade" in diagnostics_df.columns
        and "final_signal_after_filters" in diagnostics_df.columns
    ):
        print(f"{'─'*55}")
        print("  ENTRY QUALITY GRADE VS FINAL SIGNAL:")

        table = pd.crosstab(
            diagnostics_df["entry_quality_grade"].fillna("N/A"),
            diagnostics_df["final_signal_after_filters"].fillna("N/A"),
        )

        if table.empty:
            print("  Ma'lumot yo‘q.")
        else:
            print(table.to_string())

    # ---------------------------------------------------------
    # FILTER SETTINGS SNAPSHOT
    # ---------------------------------------------------------
    setting_columns = [
        "enable_market_regime_filter",
        "enable_trend_direction_filter",
        "enable_quality_score_filter",
        "enable_conflict_score_filter",
        "enable_entry_quality_filter",
        "min_quality_score",
        "max_conflict_score",
        "min_entry_quality_score",
    ]

    existing_setting_columns = [
        col for col in setting_columns if col in diagnostics_df.columns
    ]

    if existing_setting_columns:
        print(f"{'─'*55}")
        print("  FILTER SETTINGS SNAPSHOT:")

        latest_settings = diagnostics_df[existing_setting_columns].tail(1).iloc[0]

        for col in existing_setting_columns:
            print(f"  {col}: {latest_settings[col]}")

    print(f"{'='*55}\n")

def print_tuning_recommendations(diagnostics_df: pd.DataFrame, trades_df: pd.DataFrame):
    """
    Backtest va diagnostics natijalariga qarab tuning tavsiyalarini chiqaradi.
    Bu avtomatik qaror emas, faqat keyingi test uchun yo'nalish beradi.
    """
    print(f"\n{'='*55}")
    print("  TUNING RECOMMENDATIONS")
    print(f"{'='*55}")

    recommendations = []

    # ---------------------------------------------------------
    # 1. Diagnostics bo'yicha filter qattiqligini baholash
    # ---------------------------------------------------------
    if diagnostics_df is not None and not diagnostics_df.empty:
        total_diag = len(diagnostics_df)

        if "block_reason" in diagnostics_df.columns:
            block_series = (
                diagnostics_df["block_reason"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            blocked_count = int((block_series != "").sum())
            blocked_pct = (blocked_count / total_diag) * 100 if total_diag > 0 else 0

            recommendations.append(
                f"Diagnostics: {blocked_count}/{total_diag} yozuv bloklangan ({blocked_pct:.1f}%)."
            )

            block_counts = (
                block_series.replace("", "NOT_BLOCKED")
                .value_counts()
            )

            if "QUALITY_SCORE" in block_counts:
                quality_block_pct = (block_counts["QUALITY_SCORE"] / total_diag) * 100

                if quality_block_pct >= 20:
                    recommendations.append(
                        "QUALITY_SCORE juda ko'p signalni bloklayapti. "
                        "Agar signal juda kamayib ketgan bo'lsa, config.py da "
                        "MIN_QUALITY_SCORE ni 65 dan 60 ga tushirib alohida test qiling."
                    )
                elif quality_block_pct <= 5:
                    recommendations.append(
                        "QUALITY_SCORE kam bloklayapti. Agar sifatsiz signal ko'p bo'lsa, "
                        "MIN_QUALITY_SCORE ni 70 ga ko'tirib test qilish mumkin."
                    )

            if "CONFLICT" in block_counts:
                conflict_block_pct = (block_counts["CONFLICT"] / total_diag) * 100

                if conflict_block_pct >= 15:
                    recommendations.append(
                        "CONFLICT filter ko'p signalni bloklayapti. "
                        "Agar yaxshi signallar ham kesilayotgan bo'lsa, "
                        "MAX_CONFLICT_SCORE ni 35 dan 40 yoki 45 ga ko'tirib test qiling."
                    )

            if "ENTRY_QUALITY" in block_counts:
                entry_block_pct = (block_counts["ENTRY_QUALITY"] / total_diag) * 100

                if entry_block_pct >= 15:
                    recommendations.append(
                        "ENTRY_QUALITY filter ko'p bloklayapti. "
                        "Entry/SL/TP hisoblash logikasini tekshiring yoki "
                        "MIN_ENTRY_QUALITY_SCORE ni 65 dan 60 ga tushirib test qiling."
                    )

            if "MARKET_REGIME" in block_counts:
                regime_block_pct = (block_counts["MARKET_REGIME"] / total_diag) * 100

                if regime_block_pct >= 20:
                    recommendations.append(
                        "MARKET_REGIME filter ko'p bloklayapti. "
                        "Bu yomon emas, lekin signal juda kam chiqsa RANGING/HIGH_VOLATILITY "
                        "qoidalarini alohida backtest bilan tekshiring."
                    )

        if (
            "market_regime" in diagnostics_df.columns
            and "final_signal_after_filters" in diagnostics_df.columns
        ):
            regime_signal_table = pd.crosstab(
                diagnostics_df["market_regime"].fillna("N/A"),
                diagnostics_df["final_signal_after_filters"].fillna("N/A"),
            )

            if "RANGING" in regime_signal_table.index:
                ranging_row = regime_signal_table.loc["RANGING"]
                ranging_buy = int(ranging_row.get("BUY", 0))
                ranging_sell = int(ranging_row.get("SELL", 0))

                if ranging_buy + ranging_sell > 0:
                    recommendations.append(
                        "RANGING regime ichida ham BUY/SELL qolgan. "
                        "Agar range bozorida loss ko'paysa, RANGING filterini qattiqroq qiling."
                    )
                else:
                    recommendations.append(
                        "RANGING regime ichida BUY/SELL deyarli qolmagan. "
                        "Trend-following yondashuv uchun bu normal."
                    )

    # ---------------------------------------------------------
    # 2. Real trade natijalari bo'yicha tavsiya
    # ---------------------------------------------------------
    if trades_df is not None and not trades_df.empty:
        total_trades = len(trades_df)
        wins = len(trades_df[trades_df["outcome"] == "WIN"])
        losses = len(trades_df[trades_df["outcome"] == "LOSS"])
        winrate = (wins / total_trades) * 100 if total_trades > 0 else 0

        pnl_sum = trades_df["pnl_pips"].sum() if "pnl_pips" in trades_df.columns else 0

        recommendations.append(
            f"Trade result: total={total_trades}, winrate={winrate:.1f}%, net_pnl={pnl_sum:+.1f} pip."
        )

        if total_trades < 20:
            recommendations.append(
                "Signal soni hali kam. Threshold bo'yicha xulosa qilishdan oldin "
                "ko'proq bars bilan backtest qiling, masalan bars=5000 yoki bars=10000."
            )

        if "signal" in trades_df.columns:
            for direction in ["BUY", "SELL"]:
                side_df = trades_df[trades_df["signal"] == direction]

                if side_df.empty:
                    recommendations.append(
                        f"{direction} signal hali yo'q yoki juda kam. "
                        f"{direction} tomonni baholash uchun sample yetarli emas."
                    )
                    continue

                side_total = len(side_df)
                side_wins = len(side_df[side_df["outcome"] == "WIN"])
                side_losses = len(side_df[side_df["outcome"] == "LOSS"])
                side_wr = (side_wins / side_total) * 100 if side_total > 0 else 0
                side_pnl = side_df["pnl_pips"].sum()

                if side_total >= 5 and side_pnl < 0:
                    recommendations.append(
                        f"{direction} signallar zarar ko'rsatgan: "
                        f"total={side_total}, WR={side_wr:.1f}%, PnL={side_pnl:+.1f}. "
                        f"{direction} uchun thresholdni kuchaytirish yoki vaqtincha bloklashni test qiling."
                    )

                if side_total >= 5 and side_pnl > 0:
                    recommendations.append(
                        f"{direction} signallar ijobiy: "
                        f"total={side_total}, WR={side_wr:.1f}%, PnL={side_pnl:+.1f}. "
                        f"Bu yo'nalish uchun setup ishlayotgan bo'lishi mumkin."
                    )

        if "r_multiple" in trades_df.columns:
            r_series = pd.to_numeric(trades_df["r_multiple"], errors="coerce").dropna()

            if not r_series.empty:
                avg_r = r_series.mean()
                total_r = r_series.sum()

                if avg_r <= 0:
                    recommendations.append(
                        f"Avg R manfiy yoki nolga yaqin ({avg_r:+.2f}R). "
                        "Strategiya expectancy jihatdan hali kuchsiz. Entry quality, RR va regime filterlarni qayta tuning qiling."
                    )
                elif avg_r < 0.20:
                    recommendations.append(
                        f"Avg R past ({avg_r:+.2f}R). "
                        "Strategiya ishlashi mumkin, lekin edge kuchsiz. Quality thresholdni oshirib test qiling."
                    )
                else:
                    recommendations.append(
                        f"Avg R yaxshi ko'rinmoqda ({avg_r:+.2f}R), Total R={total_r:+.2f}R. "
                        "Endi ko'proq history va forward demo test kerak."
                    )

        if "market_regime" in trades_df.columns:
            for regime, group in trades_df.groupby("market_regime"):
                if group.empty:
                    continue

                g_total = len(group)
                g_pnl = group["pnl_pips"].sum()

                if g_total >= 5 and g_pnl < 0:
                    recommendations.append(
                        f"{regime} regime zarar ko'rsatgan: total={g_total}, PnL={g_pnl:+.1f}. "
                        "Bu regime uchun signalni bloklash yoki thresholdni kuchaytirishni test qiling."
                    )

                if g_total >= 5 and g_pnl > 0:
                    recommendations.append(
                        f"{regime} regime ijobiy: total={g_total}, PnL={g_pnl:+.1f}. "
                        "Bu regime signal uchun mos bo'lishi mumkin."
                    )

    else:
        recommendations.append(
            "Final BUY/SELL trade topilmadi. Filterlar juda qattiq bo'lishi mumkin "
            "yoki tanlangan history davrida setup bo'lmagan."
        )
        recommendations.append(
            "Avval diagnostics CSV'da block_reason taqsimotini ko'ring. "
            "Agar QUALITY_SCORE/ENTRY_QUALITY ko'p bo'lsa thresholdni pasaytirib test qiling."
        )

    if not recommendations:
        recommendations.append("Tuning uchun yetarli ma'lumot topilmadi.")

    for idx, rec in enumerate(recommendations, start=1):
        print(f"  {idx}. {rec}")

    print(f"{'='*55}\n")


def print_report(df: pd.DataFrame):
    """Backtest natijalarini chiroyli chiqarish."""
    if df.empty:
        print("Natija yo'q!")
        return

    total   = len(df)
    wins    = len(df[df["outcome"] == "WIN"])
    losses  = len(df[df["outcome"] == "LOSS"])
    timeout = len(df[df["outcome"] == "TIMEOUT"])

    winrate = wins / total * 100 if total > 0 else 0

    tp1_hits = len(df[df["tp_hit"] == 1])
    tp2_hits = len(df[df["tp_hit"] == 2])
    tp3_hits = len(df[df["tp_hit"] == 3])

    buy_trades  = df[df["signal"] == "BUY"]
    sell_trades = df[df["signal"] == "SELL"]

    buy_wins = len(buy_trades[buy_trades["outcome"] == "WIN"])
    buy_losses = len(buy_trades[buy_trades["outcome"] == "LOSS"])
    buy_timeouts = len(buy_trades[buy_trades["outcome"] == "TIMEOUT"])
    buy_net_pnl = buy_trades["pnl_pips"].sum() if not buy_trades.empty else 0

    sell_wins = len(sell_trades[sell_trades["outcome"] == "WIN"])
    sell_losses = len(sell_trades[sell_trades["outcome"] == "LOSS"])
    sell_timeouts = len(sell_trades[sell_trades["outcome"] == "TIMEOUT"])
    sell_net_pnl = sell_trades["pnl_pips"].sum() if not sell_trades.empty else 0

    total_pnl = df[df["outcome"] == "WIN"]["pnl_pips"].sum()
    total_loss = df[df["outcome"] == "LOSS"]["pnl_pips"].sum()
    net_pnl = total_pnl - abs(total_loss)

    wins_df = df[df["outcome"] == "WIN"].copy()
    losses_df = df[df["outcome"] == "LOSS"].copy()

    avg_win = wins_df["pnl_pips"].mean() if not wins_df.empty else 0
    avg_loss = losses_df["pnl_pips"].mean() if not losses_df.empty else 0

    gross_profit = total_pnl
    gross_loss = abs(total_loss)

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = None

    expectancy = df["pnl_pips"].mean() if not df.empty else 0

    avg_r = None
    total_r = None

    if "r_multiple" in df.columns:
        r_series = pd.to_numeric(df["r_multiple"], errors="coerce").dropna()
        if not r_series.empty:
            avg_r = r_series.mean()
            total_r = r_series.sum()

    equity_curve = df["pnl_pips"].cumsum()
    running_max = equity_curve.cummax()
    drawdown = equity_curve - running_max
    max_drawdown = drawdown.min() if not drawdown.empty else 0

    ready_buys = len(df[df["setup"] == "READY BUY"])
    ready_sells = len(df[df["setup"] == "READY SELL"])
    buy_watch = len(df[df["setup"] == "BUY WATCH"])
    sell_watch = len(df[df["setup"] == "SELL WATCH"])
    no_trade_count = len(df[df["setup"] == "NO TRADE"])

    avg_bars    = df["bars_held"].mean()

    avg_quality = None
    avg_entry_quality = None
    avg_conflict = None

    if "quality_score" in df.columns:
        q = pd.to_numeric(df["quality_score"], errors="coerce").dropna()
        if not q.empty:
            avg_quality = q.mean()

    if "entry_quality_score" in df.columns:
        eq = pd.to_numeric(df["entry_quality_score"], errors="coerce").dropna()
        if not eq.empty:
            avg_entry_quality = eq.mean()

    if "conflict_score" in df.columns:
        cf = pd.to_numeric(df["conflict_score"], errors="coerce").dropna()
        if not cf.empty:
            avg_conflict = cf.mean()

    print(f"\n{'='*55}")
    print(f"  BACKTEST NATIJASI — {SYMBOL} M15")
    print(f"{'='*55}")
    print(f"  Jami signallar : {total}")
    print(f"  BUY signallar  : {len(buy_trades)}")
    print(f"  SELL signallar : {len(sell_trades)}")
    print(f"  READY BUY      : {ready_buys}")
    print(f"  READY SELL     : {ready_sells}")
    print(f"  BUY WATCH      : {buy_watch}")
    print(f"  SELL WATCH     : {sell_watch}")
    print(f"  NO TRADE       : {no_trade_count}")
    print(f"  BUY W/L/T      : {buy_wins}/{buy_losses}/{buy_timeouts}")
    print(f"  BUY net PnL    : {buy_net_pnl:+.1f} pip")
    print(f"  SELL W/L/T     : {sell_wins}/{sell_losses}/{sell_timeouts}")
    print(f"  SELL net PnL   : {sell_net_pnl:+.1f} pip")
    print(f"{'─'*55}")
    print(f"  WIN            : {wins}  ({winrate:.1f}%)")
    print(f"  LOSS           : {losses}")
    print(f"  TIMEOUT        : {timeout}")
    print(f"{'─'*55}")
    print(f"  TP1 ga yetdi   : {tp1_hits}")
    print(f"  TP2 ga yetdi   : {tp2_hits}")
    print(f"  TP3 ga yetdi   : {tp3_hits}")
    print(f"{'─'*55}")
    print(f"  Jami foyda     : +{total_pnl:.1f} pip")
    print(f"  Jami zarar     : -{abs(total_loss):.1f} pip")
    print(f"  Sof natija     : {net_pnl:+.1f} pip")

    if profit_factor is not None:
        print(f"  Profit Factor  : {profit_factor:.2f}")
    else:
        print("  Profit Factor  : N/A")

    print(f"  Expectancy     : {expectancy:+.2f} pip/trade")
    if avg_r is not None:
        print(f"  Avg R          : {avg_r:+.2f}R")
    if total_r is not None:
        print(f"  Total R        : {total_r:+.2f}R")
    print(f"  Avg Win        : +{avg_win:.2f} pip")
    print(f"  Avg Loss       : {avg_loss:.2f} pip")
    print(f"  Max Drawdown   : {max_drawdown:.2f} pip")
    print(f"  O'rtacha davom : {avg_bars:.0f} sham ({avg_bars*15/60:.1f} soat)")

    print(f"{'─'*55}")
    if avg_quality is not None:
        print(f"  Avg Quality     : {avg_quality:.1f}/100")
    if avg_entry_quality is not None:
        print(f"  Avg Entry Qual. : {avg_entry_quality:.1f}/100")
    if avg_conflict is not None:
        print(f"  Avg Conflict    : {avg_conflict:.1f}")

    if "quality_grade" in df.columns:
        print(f"{'─'*55}")
        print("  Quality Grade:")
        print(df["quality_grade"].fillna("N/A").value_counts().to_string())

    if "entry_quality_grade" in df.columns:
        print(f"{'─'*55}")
        print("  Entry Grade:")
        print(df["entry_quality_grade"].fillna("N/A").value_counts().to_string())

    if "market_regime" in df.columns:
        print(f"{'─'*55}")
        print("  Market Regime:")
        print(df["market_regime"].fillna("N/A").value_counts().to_string())

    if "block_reason" in df.columns:
        print(f"{'─'*55}")
        print("  Block Reason:")
        print(
            df["block_reason"]
            .fillna("NOT_BLOCKED")
            .replace("", "NOT_BLOCKED")
            .value_counts()
            .to_string()
        )

    # ---------------------------------------------------------
    # GROUP ANALYSIS: QUALITY GRADE
    # ---------------------------------------------------------
    if "quality_grade" in df.columns:
        print(f"{'─'*55}")
        print("  RESULT BY QUALITY GRADE:")

        for grade, group in df.groupby("quality_grade"):
            if group.empty:
                continue

            g_total = len(group)
            g_wins = len(group[group["outcome"] == "WIN"])
            g_losses = len(group[group["outcome"] == "LOSS"])
            g_timeouts = len(group[group["outcome"] == "TIMEOUT"])
            g_winrate = (g_wins / g_total) * 100 if g_total > 0 else 0
            g_net_pnl = group["pnl_pips"].sum()

            if "r_multiple" in group.columns:
                g_r = pd.to_numeric(group["r_multiple"], errors="coerce").dropna()
                g_avg_r = g_r.mean() if not g_r.empty else 0
                g_total_r = g_r.sum() if not g_r.empty else 0
            else:
                g_avg_r = 0
                g_total_r = 0

            print(
                f"  {grade}: total={g_total}, "
                f"W/L/T={g_wins}/{g_losses}/{g_timeouts}, "
                f"WR={g_winrate:.1f}%, "
                f"PnL={g_net_pnl:+.1f}, "
                f"AvgR={g_avg_r:+.2f}, "
                f"TotalR={g_total_r:+.2f}"
            )

    # ---------------------------------------------------------
    # GROUP ANALYSIS: ENTRY QUALITY GRADE
    # ---------------------------------------------------------
    if "entry_quality_grade" in df.columns:
        print(f"{'─'*55}")
        print("  RESULT BY ENTRY QUALITY GRADE:")

        for grade, group in df.groupby("entry_quality_grade"):
            if group.empty:
                continue

            g_total = len(group)
            g_wins = len(group[group["outcome"] == "WIN"])
            g_losses = len(group[group["outcome"] == "LOSS"])
            g_timeouts = len(group[group["outcome"] == "TIMEOUT"])
            g_winrate = (g_wins / g_total) * 100 if g_total > 0 else 0
            g_net_pnl = group["pnl_pips"].sum()

            if "r_multiple" in group.columns:
                g_r = pd.to_numeric(group["r_multiple"], errors="coerce").dropna()
                g_avg_r = g_r.mean() if not g_r.empty else 0
                g_total_r = g_r.sum() if not g_r.empty else 0
            else:
                g_avg_r = 0
                g_total_r = 0

            print(
                f"  {grade}: total={g_total}, "
                f"W/L/T={g_wins}/{g_losses}/{g_timeouts}, "
                f"WR={g_winrate:.1f}%, "
                f"PnL={g_net_pnl:+.1f}, "
                f"AvgR={g_avg_r:+.2f}, "
                f"TotalR={g_total_r:+.2f}"
            )

    # ---------------------------------------------------------
    # GROUP ANALYSIS: MARKET REGIME
    # ---------------------------------------------------------
    if "market_regime" in df.columns:
        print(f"{'─'*55}")
        print("  RESULT BY MARKET REGIME:")

        for regime, group in df.groupby("market_regime"):
            if group.empty:
                continue

            g_total = len(group)
            g_wins = len(group[group["outcome"] == "WIN"])
            g_losses = len(group[group["outcome"] == "LOSS"])
            g_timeouts = len(group[group["outcome"] == "TIMEOUT"])
            g_winrate = (g_wins / g_total) * 100 if g_total > 0 else 0
            g_net_pnl = group["pnl_pips"].sum()

            if "r_multiple" in group.columns:
                g_r = pd.to_numeric(group["r_multiple"], errors="coerce").dropna()
                g_avg_r = g_r.mean() if not g_r.empty else 0
                g_total_r = g_r.sum() if not g_r.empty else 0
            else:
                g_avg_r = 0
                g_total_r = 0

            print(
                f"  {regime}: total={g_total}, "
                f"W/L/T={g_wins}/{g_losses}/{g_timeouts}, "
                f"WR={g_winrate:.1f}%, "
                f"PnL={g_net_pnl:+.1f}, "
                f"AvgR={g_avg_r:+.2f}, "
                f"TotalR={g_total_r:+.2f}"
            )

    # ---------------------------------------------------------
    # GROUP ANALYSIS: SIGNAL DIRECTION
    # ---------------------------------------------------------
    if "signal" in df.columns:
        print(f"{'─'*55}")
        print("  RESULT BY SIGNAL DIRECTION:")

        for direction, group in df.groupby("signal"):
            if group.empty:
                continue

            g_total = len(group)
            g_wins = len(group[group["outcome"] == "WIN"])
            g_losses = len(group[group["outcome"] == "LOSS"])
            g_timeouts = len(group[group["outcome"] == "TIMEOUT"])
            g_winrate = (g_wins / g_total) * 100 if g_total > 0 else 0
            g_net_pnl = group["pnl_pips"].sum()

            if "r_multiple" in group.columns:
                g_r = pd.to_numeric(group["r_multiple"], errors="coerce").dropna()
                g_avg_r = g_r.mean() if not g_r.empty else 0
                g_total_r = g_r.sum() if not g_r.empty else 0
            else:
                g_avg_r = 0
                g_total_r = 0

            print(
                f"  {direction}: total={g_total}, "
                f"W/L/T={g_wins}/{g_losses}/{g_timeouts}, "
                f"WR={g_winrate:.1f}%, "
                f"PnL={g_net_pnl:+.1f}, "
                f"AvgR={g_avg_r:+.2f}, "
                f"TotalR={g_total_r:+.2f}"
            )

    print(f"{'='*55}\n")

    # CSV ga saqlash
    logs_dir  = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path      = logs_dir / f"backtest_{timestamp}.csv"
    df.to_csv(path, index=False)
    print(f"  Natija saqlandi: {path}\n")


if __name__ == "__main__":
    results = run_backtest(bars=5000, warmup=150)
    print_report(results)
