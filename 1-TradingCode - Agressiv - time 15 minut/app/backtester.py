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

    for i in range(start_idx, min(start_idx + max_bars, len(df))):
        row  = df.iloc[i]
        high = row["high"]
        low  = row["low"]
        result["bars_held"] = i - start_idx + 1

        if signal == "BUY":
            if low <= sl:
                result["outcome"]  = "LOSS"
                result["pnl_pips"] = round(sl - entry, 2)
                break
            if tp3 and high >= tp3:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 3
                result["pnl_pips"] = round(tp3 - entry, 2)
                break
            if tp2 and high >= tp2:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 2
                result["pnl_pips"] = round(tp2 - entry, 2)
                break
            if tp1 and high >= tp1:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 1
                result["pnl_pips"] = round(tp1 - entry, 2)
                break

        elif signal == "SELL":
            if high >= sl:
                result["outcome"]  = "LOSS"
                result["pnl_pips"] = round(entry - sl, 2)
                break
            if tp3 and low <= tp3:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 3
                result["pnl_pips"] = round(entry - tp3, 2)
                break
            if tp2 and low <= tp2:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 2
                result["pnl_pips"] = round(entry - tp2, 2)
                break
            if tp1 and low <= tp1:
                result["outcome"]  = "WIN"
                result["tp_hit"]   = 1
                result["pnl_pips"] = round(entry - tp1, 2)
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
    h1_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 500)
    df_h1 = pd.DataFrame(h1_rates)
    df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s")
    df_h1 = add_ema(df_h1, [EMA_FAST, EMA_SLOW])

    dxy_bars = max(bars + 300, 500)
    df_dxy = get_backtest_dxy_data(dxy_bars)
    news_history = load_news_history()

    df = prepare_indicators(df)
    df = df.dropna().reset_index(drop=True)

    trades = []
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

        if signal == "BUY" and dxy_status == "STRENGTHENING":
            diagnostics["dxy_blocked"] += 1
            signal = "WAIT"

        elif signal == "SELL" and dxy_status == "WEAKENING":
            diagnostics["dxy_blocked"] += 1
            signal = "WAIT"

        if signal in ["BUY", "SELL"] and is_news_time:
            diagnostics["news_blocked"] += 1
            signal = "WAIT"

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

    if not trades:
        print("Hech qanday signal topilmadi!")
        return pd.DataFrame()

    return pd.DataFrame(trades)


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

    total_pnl   = df[df["outcome"] == "WIN"]["pnl_pips"].sum()
    total_loss  = df[df["outcome"] == "LOSS"]["pnl_pips"].sum()
    net_pnl     = total_pnl - abs(total_loss)

    ready_buys = len(df[df["setup"] == "READY BUY"])
    ready_sells = len(df[df["setup"] == "READY SELL"])
    buy_watch = len(df[df["setup"] == "BUY WATCH"])
    sell_watch = len(df[df["setup"] == "SELL WATCH"])
    no_trade_count = len(df[df["setup"] == "NO TRADE"])

    avg_bars    = df["bars_held"].mean()

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
    print(f"  O'rtacha davom : {avg_bars:.0f} sham ({avg_bars*15/60:.1f} soat)")
    print(f"{'='*55}\n")

    # CSV ga saqlash
    logs_dir  = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path      = logs_dir / f"backtest_{timestamp}.csv"
    df.to_csv(path, index=False)
    print(f"  Natija saqlandi: {path}\n")


if __name__ == "__main__":
    results = run_backtest(bars=2000, warmup=100)
    print_report(results)
