from rich.console import Console
from rich.table import Table
from datetime import datetime
from pathlib import Path
import pandas as pd
from config import SIGNAL_MODE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ENABLE_TELEGRAM_NOTIFICATIONS
from colorama import init, Fore, Style
import platform
import requests
import os
init(autoreset=True)

def _beep(frequency: int, duration_ms: int):
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(frequency, duration_ms)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass

def color_signal_text(text: str) -> str:
    t = str(text).upper()

    if "BUY" in t and "WATCH" not in t:
        return Fore.GREEN + str(text) + Style.RESET_ALL

    if "SELL" in t and "WATCH" not in t:
        return Fore.RED + str(text) + Style.RESET_ALL

    if "READY BUY" in t:
        return Fore.CYAN + str(text) + Style.RESET_ALL

    if "READY SELL" in t:
        return Fore.MAGENTA + str(text) + Style.RESET_ALL

    if "BUY WATCH" in t:
        return Fore.BLUE + str(text) + Style.RESET_ALL

    if "SELL WATCH" in t:
        return Fore.YELLOW + str(text) + Style.RESET_ALL

    if "WAIT" in t:
        return Fore.YELLOW + str(text) + Style.RESET_ALL

    if "NO TRADE" in t:
        return Fore.WHITE + str(text) + Style.RESET_ALL

    if "STRONG" in t:
        return Fore.GREEN + str(text) + Style.RESET_ALL

    if "MEDIUM" in t:
        return Fore.YELLOW + str(text) + Style.RESET_ALL

    if "WEAK" in t:
        return Fore.RED + str(text) + Style.RESET_ALL

    return str(text)

def play_signal_sound(setup_status: str, final_signal: str):
    if final_signal == "BUY":
        _beep(1200, 500)
        _beep(1400, 500)
        return

    if final_signal == "SELL":
        _beep(900, 500)
        _beep(700, 500)
        return

    if setup_status == "READY BUY":
        _beep(1000, 400)
        return

    if setup_status == "READY SELL":
        _beep(800, 400)
        return

console = Console()

def show_analysis_report(
    h1_timeframe_name: str,
    m15_timeframe_name: str,
    h1_trend: str,
    m15_trend: str,
    alignment_text: str,
    rsi_value: float,
    rsi_text: str,
    macd_text: str,
    candle_confirmation: str,
    support: float,
    resistance: float,
    atr_value: float,
    price_location: str,
    entry_zone_text: str,
    summary: str,
    trade_comment: str,
    setup_status: str,
    signal_strength: str,
    trade_plan: str,
    final_signal: str,
    alert_message: str,
    reason: str,
    suggested_entry,
    suggested_sl,
    suggested_tp,
    risk_reward_ratio,
):
    table = Table(title="GOLD TRADING ANALYSIS REPORT")

    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Higher Timeframe", h1_timeframe_name)
    table.add_row("Entry Timeframe", m15_timeframe_name)
    table.add_row("H1 Trend", h1_trend)
    table.add_row("M15 Trend", m15_trend)
    table.add_row("Timeframe Alignment", alignment_text)
    table.add_row("RSI", f"{rsi_value:.2f}")
    table.add_row("RSI Status", rsi_text)
    table.add_row("MACD Status", macd_text)
    table.add_row("Candle Confirmation", candle_confirmation)
    table.add_row("Support", f"{support:.2f}")
    table.add_row("Resistance", f"{resistance:.2f}")
    table.add_row("ATR", f"{atr_value:.2f}")
    table.add_row("Price Location", price_location)
    table.add_row("Entry Zone", entry_zone_text)
    table.add_row("Summary", summary)
    table.add_row("Trade Comment", trade_comment)
    table.add_row("Setup Status", setup_status)
    table.add_row("Signal Strength", signal_strength)
    table.add_row("Trade Plan", trade_plan)
    table.add_row("Final Signal", final_signal)
    table.add_row("Alert Message", alert_message)
    table.add_row("Reason", reason)

    if suggested_entry is not None:
        table.add_row("Suggested Entry", f"{suggested_entry:.2f}")
    else:
        table.add_row("Suggested Entry", "N/A")

    if suggested_sl is not None:
        table.add_row("Suggested Stop Loss", f"{suggested_sl:.2f}")
    else:
        table.add_row("Suggested Stop Loss", "N/A")

    if suggested_tp is not None:
        table.add_row("Suggested Take Profit", f"{suggested_tp:.2f}")
    else:
        table.add_row("Suggested Take Profit", "N/A")

    if risk_reward_ratio is not None:
        table.add_row("Risk/Reward Ratio", f"{risk_reward_ratio:.2f}")
    else:
        table.add_row("Risk/Reward Ratio", "N/A")

    console.print(table)

def show_price_table(df):
    if df is None or df.empty:
        print("Narx jadvali uchun ma'lumot yo'q.")
        return

    required_columns = [
        "time", "open", "high", "low", "close",
        "EMA_20", "EMA_50", "RSI", "MACD", "MACD_signal"
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(
            "Narx jadvali uchun indikator ustunlari hali yo'q: "
            + ", ".join(missing_columns)
        )
        return

    table = Table(title="XAUUSD M15 - Last 5 Bars")

    for col in required_columns:
        table.add_column(col, style="cyan")

    last_rows = df.tail(5)

    for _, row in last_rows.iterrows():
        table.add_row(
            str(row["time"]),
            f"{row['open']:.2f}",
            f"{row['high']:.2f}",
            f"{row['low']:.2f}",
            f"{row['close']:.2f}",
            f"{row['EMA_20']:.2f}",
            f"{row['EMA_50']:.2f}",
            f"{row['RSI']:.2f}",
            f"{row['MACD']:.2f}",
            f"{row['MACD_signal']:.2f}",
        )

    console.print(table)


def save_analysis_to_file(result: dict):
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_path = logs_dir / f"analysis_{timestamp}.txt"

    if "m15_df" in result and result["m15_df"] is not None and not result["m15_df"].empty:
        m15_df = result["m15_df"].tail(5)
    else:
        m15_df = pd.DataFrame()

    lines = []
    lines.append("GOLD TRADING ANALYSIS REPORT")
    lines.append("=" * 50)
    lines.append("")
    lines.append("XAUUSD M15 - Last 5 Bars")
    lines.append("-" * 50)
    if m15_df.empty:
        lines.append("M15 bar ma'lumoti mavjud emas.")
    else:
        lines.append(m15_df.to_string(index=False))
    lines.append("")
    lines.append("FINAL ANALYSIS")
    lines.append("-" * 50)
    lines.append(f"Higher Timeframe: {result['h1_timeframe_name']}")
    lines.append(f"Entry Timeframe: {result['m15_timeframe_name']}")
    lines.append(f"H1 Trend: {result['h1_trend']}")
    lines.append(f"M15 Trend: {result['m15_trend']}")
    lines.append(f"D1 Trend: {result.get('d1_trend', 'N/A')}")
    lines.append(f"DXY Status: {result.get('dxy_status', 'N/A')}")
    lines.append(f"News Time: {result.get('is_news_time', False)}")
    lines.append(f"News Reason: {result.get('news_reason', 'N/A')}")
    lines.append(f"Timeframe Alignment: {result['alignment_text']}")
    lines.append(f"RSI: {result['last_rsi']:.2f}")
    lines.append(f"RSI Status: {result['rsi_text']}")
    lines.append(f"MACD Status: {result['macd_text']}")
    lines.append(f"Candle Confirmation: {result['candle_confirmation']}")
    lines.append(f"Support: {result['support']:.2f}")
    lines.append(f"Resistance: {result['resistance']:.2f}")
    lines.append(f"ATR: {result['atr_value']:.2f}")
    lines.append(f"Price Location: {result['price_location']}")
    lines.append(f"Entry Zone: {result['entry_zone_text']}")
    lines.append(f"Summary: {result['summary']}")
    lines.append(f"Trade Comment: {result['trade_comment']}")
    lines.append(f"Setup Status: {result['setup_status']}")
    lines.append(f"Signal Strength: {result['signal_strength']}")
    lines.append(f"Trade Plan: {result['trade_plan']}")
    lines.append(f"Final Signal: {result['final_signal']}")
    lines.append(f"Alert Message: {result['alert_message']}")
    lines.append(f"Reason: {result['reason']}")
    lines.append(f"Suggested Entry: {result['suggested_entry'] if result['suggested_entry'] is not None else 'N/A'}")
    lines.append(f"Suggested Stop Loss: {result['suggested_sl'] if result['suggested_sl'] is not None else 'N/A'}")
    lines.append(f"Suggested Take Profit: {result['suggested_tp'] if result['suggested_tp'] is not None else 'N/A'}")
    lines.append(f"Risk/Reward Ratio: {result['risk_reward_ratio'] if result['risk_reward_ratio'] is not None else 'N/A'}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    cleanup_old_logs(max_files=30)
    print(f"\nAnalysis faylga saqlandi: {file_path}")


def cleanup_old_logs(max_files: int = 30):
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    log_files = sorted(logs_dir.glob("analysis_*.txt"), key=lambda f: f.stat().st_mtime)

    while len(log_files) > max_files:
        oldest_file = log_files.pop(0)
        oldest_file.unlink()

def save_bars_to_csv(result: dict):

    if "m15_df" not in result or result["m15_df"] is None or result["m15_df"].empty:
        print("Bars CSV saqlanmadi: m15_df yo'q.")
        return

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_path = logs_dir / f"bars_{timestamp}.csv"

    result["m15_df"].tail(5).to_csv(file_path, index=False)

    cleanup_old_logs(max_files=30)
    print(f"Bars CSV faylga saqlandi: {file_path}")

def _normalize_candle_time(raw_value, entry_tf: str) -> str:
    """
    Write time ni candle time ga aylantiradi.
    M15 uchun 00/15/30/45 ga floor qiladi.
    """
    try:
        ts = pd.to_datetime(raw_value)
    except Exception:
        ts = pd.to_datetime(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    tf = str(entry_tf).upper().strip()

    if tf == "M15":
        ts = ts.floor("15min")
    elif tf == "H1":
        ts = ts.floor("1h")
    elif tf == "D1":
        ts = ts.floor("1D")

    return ts.strftime("%Y-%m-%d %H:%M:%S")


def save_signal_journal(result, filepath="logs/signal_journal.csv"):
    """
    Signal journalni qat'iy schema bilan yozadi.
    - candle time va write time alohida saqlanadi
    - duplicate candle/signal yozuvlarini qayta append qilmaydi
    - outcome tracker uchun backward compatible ustunlar saqlanadi
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    write_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_tf = str(result.get("entry_tf", "M15")).upper().strip()

    raw_candle_time = result.get("signal_candle_time") or result.get("time") or write_time
    candle_time = _normalize_candle_time(raw_candle_time, entry_tf)

    final_signal = str(result.get("final_signal", "")).upper().strip()
    setup_status = str(result.get("setup_status", "")).strip()

    default_outcome = "PENDING" if final_signal in ["BUY", "SELL"] else ""

    row = {
        "time": candle_time,
        "candle_time": candle_time,
        "write_time": write_time,
        "symbol": result.get("symbol", ""),
        "higher_tf": result.get("higher_tf", ""),
        "entry_tf": entry_tf,
        "h1_trend": result.get("h1_trend", ""),
        "m15_trend": result.get("m15_trend", ""),
        "d1_trend": result.get("d1_trend", ""),
        "setup_status": setup_status,
        "signal_strength": result.get("signal_strength", ""),
        "final_signal": final_signal,
        "signal_mode": result.get("signal_mode", "normal"),
        "actionable": result.get("actionable", "NO"),
        "hot_signal": result.get("hot_signal", "NO"),

        "entry_price": result.get("suggested_entry", None),
        "stop_loss": result.get("suggested_sl", None),
        "take_profit": result.get("suggested_tp", None),
        "suggested_entry": result.get("suggested_entry", None),
        "suggested_sl": result.get("suggested_sl", None),
        "suggested_tp": result.get("suggested_tp", None),
        "tp1": result.get("tp1", None),
        "tp2": result.get("tp2", None),
        "tp3": result.get("tp3", None),
        "risk_reward_ratio": result.get("risk_reward_ratio", None),

        "dxy_status": result.get("dxy_status", ""),
        "news_blocked": result.get("is_news_time", result.get("news_blocked", "")),
        "news_reason": result.get("news_reason", ""),
        "confluence_score": result.get("confluence_score", ""),
        "confluence_text": result.get("confluence_text", ""),
        "ml_approved": result.get("ml_approved", ""),
        "ml_probability": result.get("ml_probability", ""),
        "session_status": result.get("session_status", result.get("session", "")),
        "volume_status": result.get("volume_status", ""),
        "stoch_rsi_signal": result.get("stoch_rsi_signal", result.get("stoch_rsi", "")),
        "divergence_text": result.get("divergence_text", ""),
        "market_structure": result.get("market_structure", ""),
        "order_block": result.get("order_block", ""),
        "liquidity_zones": result.get("liquidity_zones", ""),
        "fvg_text": result.get("fvg_text", ""),
        "breaker_block": result.get("breaker_block", ""),
        "imbalance_fill": result.get("imbalance_fill", ""),
        "wyckoff_phase": result.get("wyckoff_phase", ""),
        "reason": result.get("reason", ""),
        "alert_message": result.get("alert_message", ""),
        "trade_comment": result.get("trade_comment", ""),
        "trade_plan": result.get("trade_plan", ""),
        "summary": result.get("summary", ""),
        "outcome": result.get("outcome", default_outcome),
    }

    for k, v in list(row.items()):
        if isinstance(v, str) and v.strip() == "":
            row[k] = None

    ordered_columns = list(row.keys())

    if os.path.exists(filepath):
        try:
            existing = pd.read_csv(filepath)
        except Exception:
            existing = pd.DataFrame(columns=ordered_columns)
    else:
        existing = pd.DataFrame(columns=ordered_columns)

    for col in ordered_columns:
        if col not in existing.columns:
            existing[col] = ""

    # CSV dan kelgan float/int dtype ustunlarga keyin string ham yozilishi mumkin,
    # shuning uchun update/appendingdan oldin object dtype ga o'tkazamiz.
    existing = existing.astype(object)

    candle_mask = (
        (existing["symbol"].astype(str) == str(row["symbol"])) &
        (existing["entry_tf"].astype(str) == str(row["entry_tf"])) &
        (existing["candle_time"].astype(str) == str(row["candle_time"]))
    )

    if candle_mask.any():
        idx = existing[candle_mask].index[-1]

        existing_final_signal = str(existing.at[idx, "final_signal"]).upper().strip()
        new_final_signal = str(row["final_signal"]).upper().strip()

        existing_outcome = str(existing.at[idx, "outcome"]).strip() if "outcome" in existing.columns else ""

        # Agar candle bo'yicha oldin actionable BUY/SELL yozilgan bo'lsa,
        # keyin kelgan WAIT bilan uni bosib yubormaymiz.
        preserve_actionable_signal = (
            existing_final_signal in ["BUY", "SELL"]
            and new_final_signal == "WAIT"
        )

        for col, value in row.items():
            if col == "outcome" and existing_outcome:
                continue

            if preserve_actionable_signal and col in [
                "final_signal",
                "setup_status",
                "signal_strength",
                "entry_price",
                "stop_loss",
                "take_profit",
                "suggested_entry",
                "suggested_sl",
                "suggested_tp",
                "tp1",
                "tp2",
                "tp3",
                "risk_reward_ratio",
                "reason",
                "alert_message",
                "trade_comment",
                "trade_plan",
                "summary",
            ]:
                continue

            existing.at[idx, col] = value
    else:
        existing = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)

    final_columns = ordered_columns + [c for c in existing.columns if c not in ordered_columns]
    existing = existing[final_columns]

    existing.to_csv(filepath, index=False)

def show_signal_stats():
    file_path = Path("logs") / "signal_journal.csv"

    if not file_path.exists():
        print("Signal jurnal topilmadi.")
        return

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Signal statistikani o‘qishda xatolik: {e}")
        print("Ehtimol signal_journal.csv eski va yangi format aralashib ketgan.")
        print("logs/signal_journal.csv faylini o‘chirib, qayta yaratib ko‘ring.")
        return

    if df.empty:
        print("Signal jurnal bo‘sh.")
        return

    print("\nSIGNAL STATISTICS")
    print("-----------------")
    print(f"Jami signal yozuvlari: {len(df)}")

    if "final_signal" in df.columns:
        print("\nFinal Signal statistikasi:")
        print(df["final_signal"].value_counts().to_string())

    if "setup_status" in df.columns:
        print("\nSetup Status statistikasi:")
        print(df["setup_status"].value_counts().to_string())

    if "signal_strength" in df.columns:
        print("\nSignal Strength statistikasi:")
        print(df["signal_strength"].value_counts().to_string())

    if "signal_mode" in df.columns:
        print("\nSignal Mode statistikasi:")
        print(df["signal_mode"].value_counts().to_string())

    if "setup_status" in df.columns:
        ready_statuses = ["READY BUY", "READY SELL"]
        ready_df = df[df["setup_status"].isin(ready_statuses)]

        print("\nREADY SIGNAL statistikasi:")
        if ready_df.empty:
            print("Hozircha READY BUY yoki READY SELL yo‘q.")
        else:
            print(ready_df["setup_status"].value_counts().to_string())

        actionable_statuses = ["BUY WATCH", "SELL WATCH", "READY BUY", "READY SELL"]
        actionable_df = df[df["setup_status"].isin(actionable_statuses)]

        print("\nACTIONABLE SIGNAL statistikasi:")
        if actionable_df.empty:
            print("Hozircha actionable signal yo‘q.")
        else:
            print(actionable_df["setup_status"].value_counts().to_string())

        hot_statuses = ["READY BUY", "READY SELL"]
        hot_df = df[df["setup_status"].isin(hot_statuses)]

        print("\nHOT SIGNAL statistikasi:")
        if hot_df.empty:
            print("Hozircha READY BUY yoki READY SELL yo‘q.")
        else:
            print(hot_df["setup_status"].value_counts().to_string())

def show_recent_signals(limit: int = 10):
    file_path = Path("logs/signal_journal.csv")

    if not file_path.exists():
        print("\nOxirgi signallar topilmadi. signal_journal.csv hali yaratilmagan.\n")
        return

    try:
        df = pd.read_csv(file_path)

        if df.empty:
            print("\nSignal jurnal bo‘sh.\n")
            return

        recent_df = df.tail(limit).fillna("N/A")

        print("\nRECENT SIGNALS")
        print("-" * 40)

        columns_to_show = [
            "time",
            "symbol",
            "h1_trend",
            "m15_trend",
            "setup_status",
            "signal_strength",
            "final_signal",
            "actionable",
            "hot_signal",
            "signal_mode",
        ]

        existing_columns = [col for col in columns_to_show if col in recent_df.columns]

        if not existing_columns:
            print("Ko‘rsatish uchun mos ustunlar topilmadi.")
            return

        print(recent_df[existing_columns].to_string(index=False))

    except Exception as e:
        print(f"\nOxirgi signallarni o‘qishda xatolik: {e}\n")

def show_actionable_signals(limit: int = 10):
    file_path = Path("logs/signal_journal.csv")

    if not file_path.exists():
        print("\nACTIONABLE SIGNALS topilmadi. signal_journal.csv hali yaratilmagan.\n")
        return

    try:
        df = pd.read_csv(file_path)

        if df.empty:
            print("\nSignal jurnal bo‘sh.\n")
            return

        actionable_statuses = [
            "BUY WATCH",
            "SELL WATCH",
            "READY BUY",
            "READY SELL",
        ]

        filtered_df = df[df["setup_status"].isin(actionable_statuses)]

        if "reason_short" in filtered_df.columns:
            filtered_df["reason_short"] = filtered_df["reason_short"].astype(str).str.slice(0, 50)

        if filtered_df.empty:
            print("\nACTIONABLE SIGNALS")
            print("-" * 40)
            print("Hozircha muhim signal yo‘q.")
            return

        recent_df = filtered_df.tail(limit).copy().fillna("N/A")

        if "reason" in recent_df.columns:
            recent_df["reason_short"] = recent_df["reason"].astype(str).apply(
                lambda x: x[:60] + "..." if len(x) > 60 else x
            )

        print("\nACTIONABLE SIGNALS")
        print("-" * 40)


        columns_to_show = [
            "time",
            "symbol",
            "setup_status",
            "signal_strength",
            "final_signal",
            "actionable",
            "hot_signal",
            "signal_mode",
        ]

        existing_columns = [col for col in columns_to_show if col in recent_df.columns]

        if not existing_columns:
            print("Ko‘rsatish uchun mos ustunlar topilmadi.")
            return

        print(recent_df[existing_columns].to_string(index=False))

    except Exception as e:
        print(f"\nACTIONABLE SIGNALS ni o‘qishda xatolik: {e}\n")

def show_hot_signals(limit: int = 5):
    file_path = Path("logs/signal_journal.csv")

    if not file_path.exists():
        print("\nHOT SIGNALS topilmadi. signal_journal.csv hali yaratilmagan.\n")
        return

    try:
        df = pd.read_csv(file_path)

        if df.empty:
            print("\nHOT SIGNALS uchun jurnal bo‘sh.\n")
            return

        hot_statuses = ["READY BUY", "READY SELL"]
        filtered_df = df[df["setup_status"].isin(hot_statuses)]

        if "reason_short" in filtered_df.columns:
            filtered_df["reason_short"] = filtered_df["reason_short"].astype(str).str.slice(0, 50)

        print("\nHOT SIGNALS")
        print("-" * 40)

        if filtered_df.empty:
            print("Hozircha READY BUY yoki READY SELL yo‘q.")
            return

        recent_df = filtered_df.tail(limit).copy().fillna("N/A")

        if "reason" in recent_df.columns:
            recent_df["reason_short"] = recent_df["reason"].astype(str).apply(
                lambda x: x[:60] + "..." if len(x) > 60 else x
            )

        columns_to_show = [
            "time",
            "symbol",
            "setup_status",
            "signal_strength",
            "final_signal",
            "actionable",
            "hot_signal",
            "signal_mode",
        ]

        existing_columns = [col for col in columns_to_show if col in recent_df.columns]

        print(recent_df[existing_columns].to_string(index=False))

    except Exception as e:
        print(f"\nHOT SIGNALS ni o‘qishda xatolik: {e}\n")

def show_ready_signal_banner(result: dict):
    if result["setup_status"] not in ["READY BUY", "READY SELL"]:
        return

    print("\n" + "=" * 72)
    print(" " * 24 + "READY SIGNAL ALERT")
    print("=" * 72)
    print(f"Symbol       : {result['symbol']}")
    print(f"Higher TF    : {result['h1_timeframe_name']}")
    print(f"Entry TF     : {result['m15_timeframe_name']}")
    print(f"Setup Status : {color_signal_text(result['setup_status'])}")
    print(f"Final Signal : {color_signal_text(result['final_signal'])}")
    print(f"Strength     : {color_signal_text(result['signal_strength'])}")
    print(f"Entry        : {result['suggested_entry']}")
    print(f"Stop Loss    : {result['suggested_sl']}")
    print(f"Take Profit  : {result['suggested_tp']}")
    print(f"RR Ratio     : {result['risk_reward_ratio']}")
    print(f"Reason       : {result['reason']}")
    print(f"Alert        : {result['alert_message']}")
    print("=" * 72 + "\n")

def show_final_decision(
    h1_timeframe_name: str,
    m15_timeframe_name: str,
    final_signal: str,
    setup_status: str,
    signal_strength: str,
    trade_plan: str,
    alert_message: str,
    reason: str,
    signal_mode: str,
):
    print("\nFINAL DECISION")
    print("-" * 14)
    print(f"Higher TF: {h1_timeframe_name}")
    print(f"Entry TF: {m15_timeframe_name}")
    print(f"Mode: {signal_mode}")
    print(f"Signal: {color_signal_text(final_signal)}")
    print(f"Setup: {color_signal_text(setup_status)}")
    print(f"Strength: {color_signal_text(signal_strength)}")
    print(f"Plan: {trade_plan}")
    print(f"Alert: {Fore.CYAN + alert_message + Style.RESET_ALL}")
    print(f"Reason: {Fore.WHITE + reason + Style.RESET_ALL}")

def show_run_context(symbol: str, h1_timeframe_name: str, m15_timeframe_name: str):
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"SYMBOL: {symbol}")
    print(f"HIGHER TF: {h1_timeframe_name}")
    print(f"ENTRY TF: {m15_timeframe_name}")
    print(f"TIME: {now_text}\n")

def show_signal_mode(signal_mode: str):
    print(f"SIGNAL MODE: {signal_mode}")


def show_execution_signal_banner(result: dict):
    if result["final_signal"] not in ["BUY", "SELL"]:
        return

    print("\n" + "#" * 72)
    print(" " * 22 + "EXECUTION SIGNAL TRIGGERED")
    print("#" * 72)
    print(f"Symbol       : {result['symbol']}")
    print(f"Higher TF    : {result['h1_timeframe_name']}")
    print(f"Entry TF     : {result['m15_timeframe_name']}")
    print(f"Mode         : {result.get('signal_mode', 'normal')}")
    print(f"Final Signal : {color_signal_text(result['final_signal'])}")
    print(f"Setup Status : {color_signal_text(result['setup_status'])}")
    print(f"Strength     : {color_signal_text(result['signal_strength'])}")
    print(f"Entry        : {result['suggested_entry']}")
    print(f"Stop Loss    : {result['suggested_sl']}")
    print(f"Take Profit  : {result['suggested_tp']}")
    print(f"RR Ratio     : {result['risk_reward_ratio']}")
    print(f"Reason       : {result['reason']}")
    print(f"Alert        : {result['alert_message']}")
    print("#" * 72 + "\n")


def send_telegram_alert(result: dict):
    if not ENABLE_TELEGRAM_NOTIFICATIONS:
        return

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram sozlamalari to'liq emas")
        return

    # Signal turiga qarab emoji tanlash
    signal_type = result.get('final_signal', 'WAIT')
    if signal_type == "BUY":
        emoji_sig = "🟢 BUY (Sotib olish)"
    elif signal_type == "SELL":
        emoji_sig = "🔴 SELL (Sotish)"
    else:
        # WAIT signallarini Telegramga yuborib asabga tegmasligi uchun shu joyda to'xtatish ham mumkin
        # Lekin kuzatish uchun hozircha qoldiramiz
        emoji_sig = f"⚪ {signal_type}"

    # Ma'lumotlarni xavfsiz olish (agar yo'q bo'lsa N/A yozadi)
    entry = result.get('suggested_entry', 'N/A')
    sl = result.get('suggested_sl', 'N/A')
    tp1 = result.get('tp1', 'N/A')
    tp2 = result.get('tp2', 'N/A')
    tp3 = result.get('tp3', 'N/A')
    rr = result.get('risk_reward_ratio', 'N/A')
    reason = result.get('reason', '')
    score = result.get('signal_strength', 'N/A')

    # HTML formatida chiroyli xabar yig'ish
    message = (
        f"🤖 <b>GOLD TRADING PRO</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🎯 <b>SIGNAL:</b> {emoji_sig}\n"
        f"⚡ <b>KUCHI:</b> {score}\n\n"
        f"💵 <b>ENTRY:</b> {entry}\n"
        f"🛑 <b>STOP LOSS:</b> {sl}\n\n"
        f"✅ <b>TP 1 (Xavfsiz):</b> {tp1}\n"
        f"✅ <b>TP 2 (Asosiy):</b> {tp2}\n"
        f"🚀 <b>TP 3 (Maksimal):</b> {tp3}\n\n"
        f"⚖️ <b>Risk/Reward:</b> 1:{rr}\n"
        f"📝 <b>Izoh:</b> {reason}\n"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML" # HTML formatni yoqamiz, qalin va chiroyli chiqishi uchun
    }

    try:
        import requests
        response = requests.post(url, data=data, timeout=10)
        if response.status_code != 200:
            print(f"Telegram API xatosi: {response.text}")
    except Exception as e:
        print(f"Telegram xatolik: {e}")


def send_telegram_photo(photo_path, caption):
    if not ENABLE_TELEGRAM_NOTIFICATIONS:
        return

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram sozlamalari to'liq emas")
        return

    if not os.path.exists(photo_path):
        print(f"❌ Rasm topilmadi: {photo_path}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    try:
        with open(photo_path, "rb") as photo:
            files = {"photo": photo}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
            }

            response = requests.post(url, files=files, data=data, timeout=15)

            if response.status_code == 200:
                print("✅ Rasm Telegramga yuborildi")
            else:
                print(f"❌ Telegram xatosi: {response.text}")

    except Exception as e:
        print(f"❌ Rasm yuborishda xatolik: {e}")