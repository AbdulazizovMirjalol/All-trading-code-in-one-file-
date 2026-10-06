"""
outcome_tracker.py — Signal natijalarini kuzatish.

Ishlash tartibi:
  1. signal_journal.csv dan outcome=None signallarni oladi
  2. Har signal uchun MT5 dan o'tgan shamlarni oladi
  3. TP1/TP2/TP3 yoki SL ga yetganini tekshiradi
  4. outcome ustunini to'ldiradi
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path


JOURNAL_PATH = Path("logs/signal_journal.csv")
MAX_BARS     = 100   # Signal dan keyin max 100 ta sham tekshiriladi


def connect():
    if not mt5.initialize():
        print(f"MT5 ulanmadi: {mt5.last_error()}")
        return False
    return True


def disconnect():
    mt5.shutdown()


def get_bars_after_signal(symbol: str, signal_time: datetime, bars: int = 100):
    """
    Signal vaqtidan keyingi shamlarni oladi.
    Signal chiqqan shamning o'zini emas, undan keyingilarni tekshiradi.
    """
    try:
        start_time = signal_time + timedelta(minutes=15)

        rates = mt5.copy_rates_from(
            symbol,
            mt5.TIMEFRAME_M15,
            start_time,
            bars,
        )

        if rates is None or len(rates) == 0:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    except Exception as e:
        print(f"Ma'lumot olishda xato: {e}")
        return None


def check_outcome(
    signal: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    bars_df: pd.DataFrame,
    max_bars: int = MAX_BARS,
) -> dict:
    """
    Signal natijasini tekshiradi.

    Agar TP/SL hali urilmagan bo'lsa:
      - bars soni max_bars ga yetmagan bo'lsa -> PENDING
      - bars soni max_bars ga yetgan bo'lsa -> TIMEOUT
    """
    result = {
        "outcome":   "PENDING",
        "tp_hit":    0,
        "bars_held": 0,
        "pnl_pips":  0.0,
    }

    if bars_df is None or bars_df.empty:
        return result

    for i, row in bars_df.iterrows():
        result["bars_held"] = i + 1
        high = row["high"]
        low = row["low"]

        if signal == "BUY":
            if low <= sl:
                result["outcome"] = "LOSS"
                result["pnl_pips"] = round(sl - entry, 2)
                return result

            if tp3 and high >= tp3:
                result["outcome"] = "WIN"
                result["tp_hit"] = 3
                result["pnl_pips"] = round(tp3 - entry, 2)
                return result

            if tp2 and high >= tp2:
                result["outcome"] = "WIN"
                result["tp_hit"] = 2
                result["pnl_pips"] = round(tp2 - entry, 2)
                return result

            if tp1 and high >= tp1:
                result["outcome"] = "WIN"
                result["tp_hit"] = 1
                result["pnl_pips"] = round(tp1 - entry, 2)
                return result

        elif signal == "SELL":
            if high >= sl:
                result["outcome"] = "LOSS"
                result["pnl_pips"] = round(entry - sl, 2)
                return result

            if tp3 and low <= tp3:
                result["outcome"] = "WIN"
                result["tp_hit"] = 3
                result["pnl_pips"] = round(entry - tp3, 2)
                return result

            if tp2 and low <= tp2:
                result["outcome"] = "WIN"
                result["tp_hit"] = 2
                result["pnl_pips"] = round(entry - tp2, 2)
                return result

            if tp1 and low <= tp1:
                result["outcome"] = "WIN"
                result["tp_hit"] = 1
                result["pnl_pips"] = round(entry - tp1, 2)
                return result

    if len(bars_df) >= max_bars:
        result["outcome"] = "TIMEOUT"
    else:
        result["outcome"] = "PENDING"

    return result


def _ensure_outcome_columns(df: pd.DataFrame) -> pd.DataFrame:
    required_defaults = {
        "outcome": "",
        "tp_hit": "",
        "bars_held": "",
        "pnl_pips": "",
        "last_checked_time": "",
    }

    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default

    return df


def _safe_float(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if value is None:
        return None

    text = str(value).strip()
    if text == "":
        return None

    try:
        return float(text)
    except Exception:
        return None


def _get_signal_time_from_row(row) -> datetime | None:
    raw_time = row.get("candle_time", None)

    if raw_time is None or str(raw_time).strip() == "" or str(raw_time).lower() == "nan":
        raw_time = row.get("time", None)

    try:
        if raw_time is None or str(raw_time).strip() == "":
            return None
        return pd.to_datetime(raw_time)
    except Exception:
        return None


def run_outcome_tracker():
    """
    signal_journal.csv dagi BUY/SELL signallarni
    candle_time asosida tekshiradi va outcome ni yangilaydi.
    """
    print(f"\n{'='*50}")
    print(f"  OUTCOME TRACKER BOSHLANMOQDA")
    print(f"{'='*50}\n")

    if not JOURNAL_PATH.exists():
        print("signal_journal.csv topilmadi!")
        return

    df = pd.read_csv(JOURNAL_PATH)
    df = _ensure_outcome_columns(df)

    if "final_signal" not in df.columns:
        print("final_signal ustuni topilmadi!")
        return

    df["final_signal"] = df["final_signal"].astype(str).str.upper().str.strip()

    signals_mask = df["final_signal"].isin(["BUY", "SELL"])

    pending_mask = (
        df["outcome"].isna()
        | (df["outcome"].astype(str).str.strip() == "")
        | (df["outcome"].astype(str).str.upper() == "PENDING")
    )

    pending = df[signals_mask & pending_mask].copy()

    if pending.empty:
        print("Tekshiriladigan BUY/SELL signal yo'q!")
        print_summary(df)
        return

    sort_time_col = "candle_time" if "candle_time" in pending.columns else "time"
    try:
        pending["_sort_time"] = pd.to_datetime(pending[sort_time_col], errors="coerce")
        pending = pending.sort_values("_sort_time")
    except Exception:
        pass

    print(f"Tekshiriladigan signallar: {len(pending)}\n")

    if not connect():
        return

    updated = 0

    for idx, row in pending.iterrows():
        try:
            signal = str(row.get("final_signal", "")).upper().strip()
            symbol = str(row.get("symbol", "XAUUSD")).strip() or "XAUUSD"

            entry = _safe_float(row.get("suggested_entry", row.get("entry_price", None)))
            sl = _safe_float(row.get("suggested_sl", row.get("stop_loss", None)))

            tp1 = _safe_float(row.get("tp1", None))
            tp2 = _safe_float(row.get("tp2", None))
            tp3 = _safe_float(row.get("tp3", None))

            if tp1 is None and tp2 is None and tp3 is None:
                fallback_tp = _safe_float(row.get("suggested_tp", row.get("take_profit", None)))
                tp1 = fallback_tp

            signal_time = _get_signal_time_from_row(row)

            if signal_time is None:
                df.at[idx, "outcome"] = "INVALID_TIME"
                df.at[idx, "last_checked_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            if entry is None or sl is None:
                df.at[idx, "outcome"] = "NO_DATA"
                df.at[idx, "last_checked_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                continue

            bars = get_bars_after_signal(
                symbol=symbol,
                signal_time=signal_time,
                bars=MAX_BARS,
            )

            result = check_outcome(
                signal=signal,
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                bars_df=bars,
                max_bars=MAX_BARS,
            )

            df.at[idx, "outcome"] = result["outcome"]
            df.at[idx, "tp_hit"] = result["tp_hit"]
            df.at[idx, "bars_held"] = result["bars_held"]
            df.at[idx, "pnl_pips"] = result["pnl_pips"]
            df.at[idx, "last_checked_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            updated += 1

            print(
                f"  {signal_time.strftime('%m/%d %H:%M')} | "
                f"{signal:4s} | "
                f"Entry={entry} | "
                f"{result['outcome']:7s} | "
                f"TP{result['tp_hit']} | "
                f"{result['pnl_pips']:+.1f} pip"
            )

        except Exception as e:
            print(f"  Xato [{idx}]: {e}")
            continue

    disconnect()

    df.to_csv(JOURNAL_PATH, index=False)

    print(f"\n{updated} ta signal yangilandi!")
    print(f"Saqlandi: {JOURNAL_PATH}\n")

    print_summary(df)

    from ml_model import get_training_sample_count, MIN_SAMPLES, train_model

    ready_samples = get_training_sample_count()
    print(f"ML tayyor sample: {ready_samples}/{MIN_SAMPLES}")

    if ready_samples >= MIN_SAMPLES:
        print("ML model qayta o'qitilmoqda...")
        train_model()
    else:
        print(f"ML uchun yana {MIN_SAMPLES - ready_samples} ta WIN/LOSS kerak.")


def print_summary(df: pd.DataFrame):
    """
    Umumiy statistika chiqaradi.
    """
    if "outcome" not in df.columns:
        return

    completed = df[df["outcome"].isin(["WIN", "LOSS"])]

    if completed.empty:
        print("Hali natija yo'q!")
        return

    total   = len(completed)
    wins    = len(completed[completed["outcome"] == "WIN"])
    losses  = len(completed[completed["outcome"] == "LOSS"])
    winrate = wins / total * 100 if total > 0 else 0

    total_pnl = completed["pnl_pips"].sum() if "pnl_pips" in completed.columns else 0

    print(f"\n{'='*50}")
    print(f"  OUTCOME STATISTIKA")
    print(f"{'='*50}")
    print(f"  Jami signallar : {total}")
    print(f"  WIN            : {wins}  ({winrate:.1f}%)")
    print(f"  LOSS           : {losses}")
    print(f"  Sof PnL        : {total_pnl:+.1f} pip")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    run_outcome_tracker()