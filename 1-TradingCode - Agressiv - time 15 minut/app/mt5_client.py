import MetaTrader5 as mt5
import pandas as pd

from config import SYMBOL


def connect_mt5():
    """
    MT5 ga ulanish.
    """
    if mt5.initialize():
        print("MT5 ga muvaffaqiyatli ulandi")
        return True

    error = mt5.last_error()
    print(f"MT5 ulanmayapti. Xato: {error}")
    return False


def disconnect_mt5():
    """
    MT5 ulanishni yopish.
    """
    mt5.shutdown()
    print("MT5 ulanish yopildi")


def ensure_symbol(symbol):
    """
    Symbol Market Watch da mavjudligini tekshiradi.
    """
    info = mt5.symbol_info(symbol)

    if info is None:
        print(f"Symbol topilmadi: {symbol}")
        return False

    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"Symbolni aktiv qilib bo'lmadi: {symbol}")
            return False

    return True


def get_gold_data(timeframe=mt5.TIMEFRAME_M15, bars=50):
    """
    XAUUSD uchun OHLC data olish.
    """
    if not ensure_symbol(SYMBOL):
        return None

    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) == 0:
        print(f"{SYMBOL} data olinmadi")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    return df