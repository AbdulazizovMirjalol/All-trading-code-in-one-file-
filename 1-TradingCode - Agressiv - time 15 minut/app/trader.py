import MetaTrader5 as mt5
import json
import os
from config import MAGIC_NUMBER

# Yashirin SL xotirasi uchun fayl yo'li
VIRTUAL_SL_FILE = "logs/virtual_sl_memory.json"

def _load_virtual_memory():
    if os.path.exists(VIRTUAL_SL_FILE):
        try:
            with open(VIRTUAL_SL_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def _save_virtual_memory(data):
    os.makedirs(os.path.dirname(VIRTUAL_SL_FILE), exist_ok=True)
    with open(VIRTUAL_SL_FILE, "w") as f:
        json.dump(data, f, indent=4)

def has_open_position(symbol, magic_number=MAGIC_NUMBER):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return False
    for pos in positions:
        if pos.magic == magic_number:
            return True
    return False

def close_position(ticket, comment="Closed"):
    """Bitimni bozordan yopish funksiyasi"""
    position = mt5.positions_get(ticket=ticket)
    if not position:
        return False
    
    pos = position[0]
    tick = mt5.symbol_info_tick(pos.symbol)
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

def place_split_dca_orders(symbol, signal, total_lot, atr, current_price, virtual_sl, tp, magic_number=MAGIC_NUMBER):
    """
    SPLIT ENTRY (DCA) - Agressiv botni himoya qilish:
    - Lotni ikkiga bo'ladi.
    - 1-order: Market narxidan.
    - 2-order: Orqaga qaytganda (ATR * 0.5 masofada) Limit Order.
    """
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if info is None or tick is None:
        return False, "Ma'lumot olinmadi"

    if has_open_position(symbol, magic_number):
        return False, "Aktiv bitim bor, yangisi ochilmadi."

    # Lotni bo'lish (0.01 dan kichik bo'lib ketmasligini tekshiramiz)
    half_lot = round(total_lot / 2, 2)
    if half_lot < 0.01:
        half_lot = 0.01

    # Qopqon (Limit) masofasini hisoblash (ATR ning 50% miqdorida orqaga)
    pullback_step = atr * 0.5 

    if signal == "BUY":
        m_type = mt5.ORDER_TYPE_BUY
        l_type = mt5.ORDER_TYPE_BUY_LIMIT
        m_price = tick.ask
        l_price = round(m_price - pullback_step, 2)
    else:
        m_type = mt5.ORDER_TYPE_SELL
        l_type = mt5.ORDER_TYPE_SELL_LIMIT
        m_price = tick.bid
        l_price = round(m_price + pullback_step, 2)

    memory = _load_virtual_memory()

    # 1. MARKET ORDER (Hozirgi narxdan)
    req1 = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(half_lot),
        "type": m_type,
        "price": float(m_price),
        "sl": 0.0, # Virtual SL ishlatamiz
        "tp": float(tp),
        "magic": magic_number,
        "comment": "Split 1 (Market)",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res1 = mt5.order_send(req1)

    # 2. LIMIT ORDER (Qopqon)
    req2 = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(half_lot),
        "type": l_type,
        "price": float(l_price),
        "sl": 0.0, # Virtual SL ishlatamiz
        "tp": float(tp),
        "magic": magic_number,
        "comment": "Split 2 (Limit)",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    res2 = mt5.order_send(req2)

    # Natijalarni xotiraga yozish
    success_count = 0
    if res1 and res1.retcode == mt5.TRADE_RETCODE_DONE:
        memory[str(res1.order)] = {"symbol": symbol, "signal": signal, "v_sl": virtual_sl}
        success_count += 1
    
    if res2 and res2.retcode == mt5.TRADE_RETCODE_DONE:
        # Pending orderni ham xotiraga olamiz (u ochilganda virtual SL ishlashi uchun)
        memory[str(res2.order)] = {"symbol": symbol, "signal": signal, "v_sl": virtual_sl}
        success_count += 1

    _save_virtual_memory(memory)

    if success_count > 0:
        return True, f"Split Entry bajarildi: {success_count} order tayyor. Limit narx: {l_price}"
    
    return False, "Order yuborishda xatolik."

def monitor_virtual_sl(symbol):
    """
    Har yangi shamda ishlaydi. M15 sham yopilishiga qarab Virtual SL ni tekshiradi.
    """
    memory = _load_virtual_memory()
    if not memory:
        return

    positions = mt5.positions_get(symbol=symbol)
    active_tickets = [str(p.ticket) for p in positions] if positions else []

    # Oxirgi yopilgan M15 shamni tekshirish
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, 1)
    if rates is None or len(rates) == 0:
        return
    
    last_close = rates[0]['close']
    keys_to_remove = []

    for ticket_str, data in memory.items():
        if ticket_str not in active_tickets:
            keys_to_remove.append(ticket_str)
            continue
        
        signal = data["signal"]
        v_sl = data["v_sl"]

        # Tekshiruv: Sham yopilishi Virtual SL dan o'tib ketdimi?
        is_hit = (signal == "BUY" and last_close <= v_sl) or \
                 (signal == "SELL" and last_close >= v_sl)

        if is_hit:
            print(f"🚨 [VIRTUAL SL] Sham yopilishi bo'yicha SL urildi! Ticket: {ticket_str}")
            if close_position(int(ticket_str), comment="V-SL Hit"):
                keys_to_remove.append(ticket_str)

    # Xotirani tozalash
    for k in keys_to_remove:
        memory.pop(k, None)
    _save_virtual_memory(memory)