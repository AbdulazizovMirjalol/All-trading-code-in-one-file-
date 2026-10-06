import MetaTrader5 as mt5
import time
from config import MAGIC_NUMBER

def has_open_or_pending_position(symbol, magic_number=MAGIC_NUMBER):
    """
    Ochiq bitimlar (Positions) yoki kutib turgan (Pending Orders) borligini tekshiradi.
    """
    # 1. Ochiq bitimlarni tekshirish (Buy/Sell)
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        for pos in positions:
            if pos.magic == magic_number:
                return True

    # 2. Kutib turgan Limit/Stop buyurtmalarni tekshirish
    orders = mt5.orders_get(symbol=symbol)
    if orders:
        for ord in orders:
            if ord.magic == magic_number:
                return True
                
    return False

def cancel_pending_orders(symbol, magic_number=MAGIC_NUMBER):
    """
    Berilgan belgi va magic_number ga tegishli barcha kutib turgan buyurtmalarni bekor qiladi.
    (Agar narx qopqonga yetib bormasa, tozalash uchun ishlatiladi).
    """
    orders = mt5.orders_get(symbol=symbol)
    if orders is None:
        return

    for ord in orders:
        if ord.magic == magic_number:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": ord.ticket
            }
            mt5.order_send(request)

def place_limit_order(symbol, signal, lot_size, entry_price, sl, tp, magic_number=MAGIC_NUMBER):
    """
    Hozirgi narxdan emas, kutilayotgan (Limit) narxdan kirish uchun qopqon o'rnatadi.
    """
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if info is None:
        return False, f"Symbol topilmadi: {symbol}"

    if tick is None:
        return False, f"Tick topilmadi: {symbol}"

    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            return False, f"Symbolni Market Watch ga qo'shib bo'lmadi: {symbol}"

    # Agar ochiq bitim YOKI kutayotgan limit bo'lsa, kirmaymiz! (QULFLASH)
    if has_open_or_pending_position(symbol, magic_number):
        return False, f"AUTO TRADE OFF: {symbol} bo'yicha aktiv bitim yoki Limit order bor."

    # Eskirgan Limit buyurtmalarni tozalab tashlaymiz
    cancel_pending_orders(symbol, magic_number)

    if signal == "BUY":
        order_type = mt5.ORDER_TYPE_BUY_LIMIT
        # Limit order uchun: Buy Limit narxi hozirgi ask'dan pastroq bo'lishi shart
        if entry_price >= tick.ask:
             return False, f"Buy Limit narxi ({entry_price}) hozirgi narxdan ({tick.ask}) past bo'lishi kerak!"
             
    elif signal == "SELL":
        order_type = mt5.ORDER_TYPE_SELL_LIMIT
        # Limit order uchun: Sell Limit narxi hozirgi bid'dan yuqoriroq bo'lishi shart
        if entry_price <= tick.bid:
             return False, f"Sell Limit narxi ({entry_price}) hozirgi narxdan ({tick.bid}) yuqori bo'lishi kerak!"
             
    else:
        return False, f"Noto'g'ri signal: {signal}"

    # Agar Limit qo'yilsa va u ishlamay qolsa, qachon o'chib ketishini (Expiration) belgilaymiz (Masalan, 2 soatdan keyin)
    expiration_time = int(time.time()) + (2 * 3600)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": float(entry_price),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": magic_number,
        "comment": "GoldBot LimitOrder",
        "type_time": mt5.ORDER_TIME_SPECIFIED, # Vaqt bilan o'chadigan tur
        "expiration": expiration_time,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    result = mt5.order_send(request)

    if result is None:
        return False, "order_send None qaytardi (Limit Order)"

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"Limit Order qo'yilmadi: retcode={result.retcode}, comment={result.comment}"

    return True, f"LIMIT Order muvaffaqiyatli qo'yildi: ticket={result.order} | Narx: {entry_price}"

def place_market_order(symbol, signal, lot_size, sl, tp, magic_number=MAGIC_NUMBER):
    """
    (Hozircha saqlab turamiz, agar yana bozor narxidan kirish kerak bo'lib qolsa)
    """
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if info is None:
        return False, f"Symbol topilmadi: {symbol}"

    if tick is None:
        return False, f"Tick topilmadi: {symbol}"

    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            return False, f"Symbolni Market Watch ga qo'shib bo'lmadi: {symbol}"

    if has_open_or_pending_position(symbol, magic_number):
        return False, f"AUTO TRADE OFF: {symbol} bo'yicha aktiv bitim yoki Limit order bor."

    if signal == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        if not (sl < price < tp):
            return False, "BUY uchun SL < price < TP noto'g'ri"
    elif signal == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        if not (tp < price < sl):
            return False, "SELL uchun TP < price < SL noto'g'ri"
    else:
        return False, f"Noto'g'ri signal: {signal}"

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": float(price),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": magic_number,
        "comment": "GoldBot MarketOrder",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None:
        return False, "order_send None qaytardi"

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"Market Order ochilmadi: retcode={result.retcode}, comment={result.comment}"

    return True, f"Market Order ochildi: ticket={result.order}"