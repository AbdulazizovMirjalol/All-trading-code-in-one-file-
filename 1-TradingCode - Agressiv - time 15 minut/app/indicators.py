import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    STATUS_NO_TRADE,
    STATUS_BUY_WATCH,
    STATUS_SELL_WATCH,
    STATUS_READY_BUY,
    STATUS_READY_SELL,
    SIGNAL_WEAK,
    SIGNAL_MEDIUM,
    SIGNAL_STRONG,
    FINAL_SIGNAL_BUY,
    FINAL_SIGNAL_SELL,
    FINAL_SIGNAL_WAIT,
    SIGNAL_MODE,
    SIGNAL_MODE_AGGRESSIVE,
    SIGNAL_MODE_NORMAL,
    SIGNAL_MODE_CONSERVATIVE,
    TIMEZONE,
)

def add_ema(df: pd.DataFrame, periods):
    """
    DataFramega ko'rsatilgan davrlar uchun EMA ustunlari qo'shadi.
    """
    for p in periods:
        df[f"EMA_{p}"] = df["close"].ewm(span=p, adjust=False).mean()
    return df

def detect_trend(df: pd.DataFrame, short: int, long: int) -> str:
    """
    1-QADAM YECHIMI: ANTI-LAG VA ARRA BOZOR FILTRI.
    EMA kesishishidan tashqari, joriy narxning holatini ham tekshiradi.
    """
    if df.empty or len(df) < long:
        return "Unknown"

    ema_short = df[f"EMA_{short}"].iloc[-1]
    ema_long = df[f"EMA_{long}"].iloc[-1]
    close_price = df["close"].iloc[-1]

    # UPTREND: Qisqa EMA uzunidan tepada bo'lishi VA narx ham qisqa EMAdan tepada bo'lishi shart!
    if ema_short > ema_long and close_price > ema_short:
        return "Bullish (Ko'tarilish)"
    
    # DOWNTREND: Qisqa EMA uzunidan pastda bo'lishi VA narx ham qisqa EMAdan pastda bo'lishi shart!
    elif ema_short < ema_long and close_price < ema_short:
        return "Bearish (Tushish)"
    
    # Qolgan barcha holatlar (narx chiziqlar o'rtasida qisilib qolsa) - ARRA BOZOR
    else:
        return "Sideways (Range)"
    
def add_rsi(df: pd.DataFrame, period: int = 14):
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, float("inf"))
    df["RSI"] = 100 - (100 / (1 + rs))

    return df

def interpret_rsi(rsi_value: float) -> str:
    if rsi_value >= 70:
        return "Overbought (bozor juda qizigan)"
    elif rsi_value <= 30:
        return "Oversold (bozor juda tushgan)"
    elif rsi_value > 50:
        return "Bullish momentum"
    elif rsi_value < 50:
        return "Bearish momentum"
    else:
        return "Neutral"
    
def generate_summary(
    h1_trend: str,
    m15_trend: str,
    rsi_value: float,
    macd_text: str,
    current_price: float,
    support: float,
    resistance: float
) -> str:
    distance_to_support = abs(current_price - support)
    distance_to_resistance = abs(resistance - current_price)

    bullish_rsi = rsi_value > 50
    bearish_rsi = rsi_value < 50
    bullish_macd = "Bullish" in macd_text
    bearish_macd = "Bearish" in macd_text

    bullish_alignment = "Bullish" in h1_trend and "Bullish" in m15_trend
    bearish_alignment = "Bearish" in h1_trend and "Bearish" in m15_trend
    mixed_bullish = "Bullish" in h1_trend and "Bearish" in m15_trend
    mixed_bearish = "Bearish" in h1_trend and "Bullish" in m15_trend

    if bullish_alignment and bullish_rsi and bullish_macd:
        if distance_to_resistance < distance_to_support:
            return "H1 va M15 bullish alignmentda. RSI va MACD ham bullish. Narx resistance ga yaqin, breakout kuzatish kerak."
        return "H1 va M15 bullish alignmentda. RSI va MACD ham bullish. Bozor yuqoriga bosim ko'rsatmoqda."

    elif bearish_alignment and bearish_rsi and bearish_macd:
        if distance_to_support < distance_to_resistance:
            return "H1 va M15 bearish alignmentda. RSI va MACD ham bearish. Narx support ga yaqin, breakdown xavfi bor."
        return "H1 va M15 bearish alignmentda. RSI va MACD ham bearish. Bozor pastga bosim ko'rsatmoqda."

    elif bullish_alignment and bullish_rsi and bearish_macd:
        return "H1 va M15 bullish alignmentda, RSI bullish, lekin MACD zaiflashishni ko'rsatmoqda."

    elif bearish_alignment and bearish_rsi and bullish_macd:
        return "H1 va M15 bearish alignmentda, RSI bearish, lekin MACD tiklanishga urinmoqda."

    elif mixed_bullish:
        return "H1 bullish, lekin M15 zaiflashgan. Bu pullback yoki vaqtinchalik tuzatish bo'lishi mumkin."

    elif mixed_bearish:
        return "H1 bearish, lekin M15 tiklanmoqda. Bu counter-trend rebound bo'lishi mumkin."

    elif "Bullish" in m15_trend and bearish_rsi:
        return "M15 trend bullish, lekin momentum zaiflashgan."

    elif "Bearish" in m15_trend and bullish_rsi:
        return "M15 trend bearish, lekin momentum tiklanishga urinmoqda."

    else:
        return "Bozor noaniq yoki range holatda."
    
def generate_trade_comment(
    h1_trend: str,
    m15_trend: str,
    rsi_text: str,
    macd_text: str,
    price_location: str,
    entry_zone_text: str,
    setup_status: str
) -> str:
    if setup_status == STATUS_READY_BUY:
        return "Buy setup tayyor. Trend, momentum va candle confirmation buy tomonida."

    elif setup_status == STATUS_BUY_WATCH:
        return "Buy setup shakllanmoqda. Support/EMA zonasi yaqinida kuzatish kerak."

    elif setup_status == STATUS_READY_SELL:
        return "Sell setup tayyor. Trend, momentum va candle confirmation sell tomonida."

    elif setup_status == STATUS_SELL_WATCH:
        return "Sell setup shakllanmoqda. Resistance/EMA zonasi yaqinida kuzatish kerak."

    else:
        return "Hozircha aniq trade setup yo‘q. Shoshilmasdan kutish kerak."
    
def detect_setup_status(
    h1_trend: str,
    m15_trend: str,
    rsi_text: str,
    macd_text: str,
    price_location: str,
    entry_zone_text: str,
    candle_confirmation: str,
) -> str:
    """
    2-QADAM YECHIMI: ESKI BOT MANTIG'I (NO TRADE -> WATCH -> READY)
    Faqat H1/M15 Trendi va Entry Zonaga qaraydi. Ortiqcha indikatorlar chalg'itmaydi.
    """
    # Trendlarni aniqlaymiz
    h1_up = "Bullish" in h1_trend
    h1_down = "Bearish" in h1_trend
    m15_up = "Bullish" in m15_trend
    m15_down = "Bearish" in m15_trend

    # Narx bizning qulay zonamizga (Support, Resistance yoki EMA ga) kelganini tekshiramiz
    zone_lower = str(entry_zone_text).lower()
    in_buy_zone = "support" in zone_lower or "ema" in zone_lower or "bullish" in zone_lower
    in_sell_zone = "resistance" in zone_lower or "ema" in zone_lower or "bearish" in zone_lower

    # 1. BUY STSENARIY (Ko'tarilish)
    if h1_up and m15_up:
        if in_buy_zone:
            return STATUS_READY_BUY  # Hamma narsa mos, narx zonada -> Qurol o'qlandi (READY)
        else:
            return STATUS_BUY_WATCH  # Trend tepaga, lekin narx hali zonaga tushmadi -> Kutamiz (WATCH)

    # 2. SELL STSENARIY (Tushish)
    elif h1_down and m15_down:
        if in_sell_zone:
            return STATUS_READY_SELL # Hamma narsa mos, narx zonada -> Qurol o'qlandi (READY)
        else:
            return STATUS_SELL_WATCH # Trend pastga, lekin narx hali zonaga chiqmadi -> Kutamiz (WATCH)

    # 3. ZIDDIYAT YOKI ARRA BOZOR
    return STATUS_NO_TRADE # Trendlar har xil yoki bozor qotib qolgan -> Dam olamiz
            

def generate_trade_plan(
    setup_status: str,
    signal_strength: str,
    price_location: str,
) -> str:
    if setup_status == STATUS_READY_BUY:
        return "Buy setup tayyor. Entry, SL va TP asosida buy ko'rib chiqilishi mumkin."

    if setup_status == STATUS_READY_SELL:
        return "Sell setup tayyor. Entry, SL va TP asosida sell ko'rib chiqilishi mumkin."

    if setup_status == STATUS_BUY_WATCH:
        return "Buy setup shakllanmoqda. Support/EMA yaqinida kuzatish kerak."

    if setup_status == STATUS_SELL_WATCH:
        return "Sell setup shakllanmoqda. Resistance/EMA yaqinida kuzatish kerak."

    return "Hozircha trade ochish tavsiya etilmaydi."
    
def add_macd(df: pd.DataFrame):
    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()

    df["MACD"] = ema_12 - ema_26
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    return df

def add_atr(df: pd.DataFrame, period: int = 14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    return df


def interpret_macd(df: pd.DataFrame) -> str:
    macd_value = df["MACD"].iloc[-1]
    signal_value = df["MACD_signal"].iloc[-1]

    if macd_value > signal_value:
        return "Bullish MACD momentum"
    elif macd_value < signal_value:
        return "Bearish MACD momentum"
    else:
        return "Neutral MACD"
    
def find_support_resistance(df: pd.DataFrame):
    """
    PRO YONDASHUV: Haqiqiy Market Structure (Swing) zonalarini topish.
    Oddiy oxirgi 20 ta sham emas, balki narx qaytgan kuchli 'Pivot' nuqtalarni qidiradi.
    """
    df = df.copy()
    
    # Swing High va Swing Low (Fractals) ni aniqlash
    # Sham o'zidan oldingi va keyingi 2 ta shamdan baland/past bo'lsa - bu kuchli zona hisoblanadi
    df['Swing_High'] = df['high'][(df['high'].shift(1) < df['high']) & (df['high'].shift(2) < df['high']) & 
                                  (df['high'].shift(-1) < df['high']) & (df['high'].shift(-2) < df['high'])]
    
    df['Swing_Low'] = df['low'][(df['low'].shift(1) > df['low']) & (df['low'].shift(2) > df['low']) & 
                                (df['low'].shift(-1) > df['low']) & (df['low'].shift(-2) > df['low'])]
    
    # Eng so'nggi tasdiqlangan kuchli Liquidity / Burilish zonalari
    recent_resistance = df['Swing_High'].dropna().tail(2).max() # So'nggi 2 ta kuchli tepalikning eng balandi
    recent_support = df['Swing_Low'].dropna().tail(2).min()     # So'nggi 2 ta kuchli pastlikning eng pasti
    
    # Fallback (Xavfsizlik tizimi): Agar bozor juda kuchli impulsiv trendda bo'lib, 
    # hali swing bermagan bo'lsa, oxirgi 30 ta shamdan qidiramiz.
    if pd.isna(recent_resistance):
        recent_resistance = df["high"].tail(30).max()
    if pd.isna(recent_support):
        recent_support = df["low"].tail(30).min()
        
    return recent_support, recent_resistance

def analyze_timeframe_alignment(h1_trend: str, m15_trend: str) -> str:
    if "Bullish" in h1_trend and "Bullish" in m15_trend:
        return "H1 va M15 bir tomonda. Bullish alignment kuchli."
    elif "Bearish" in h1_trend and "Bearish" in m15_trend:
        return "H1 va M15 bir tomonda. Bearish alignment kuchli."
    elif "Bullish" in h1_trend and "Bearish" in m15_trend:
        return "H1 bullish, M15 bearish. Bu pullback yoki vaqtinchalik tuzatish bo'lishi mumkin."
    elif "Bearish" in h1_trend and "Bullish" in m15_trend:
        return "H1 bearish, M15 bullish. Bu counter-trend rebound bo'lishi mumkin."
    else:
        return "Timeframe alignment noaniq."
    
def detect_price_location(current_price: float, support: float, resistance: float) -> str:
    distance_to_support = abs(current_price - support)
    distance_to_resistance = abs(resistance - current_price)
    total_range = resistance - support

    if total_range == 0:
        return "Narx diapazoni aniqlanmadi."

    support_ratio = distance_to_support / total_range
    resistance_ratio = distance_to_resistance / total_range

    if support_ratio < 0.25:
        return "Narx support ga yaqin."
    elif resistance_ratio < 0.25:
        return "Narx resistance ga yaqin."
    else:
        return "Narx support va resistance oralig'ida."
    
def detect_entry_zone(
    df: pd.DataFrame,
    trend: str,
    current_price: float,
    ema20: float,
    support: float,
    resistance: float,
    atr: float
) -> str:
    distance_to_ema20 = abs(current_price - ema20)
    distance_to_support = abs(current_price - support)
    distance_to_resistance = abs(resistance - current_price)
    threshold = atr if atr and atr > 0 else 5.0

    fvg_type, fvg_bottom, fvg_top = find_latest_fvg(df)

    near_bullish_fvg = False
    near_bearish_fvg = False

    if fvg_type == "Bullish FVG" and fvg_bottom is not None and fvg_top is not None:
        near_bullish_fvg = (
            fvg_bottom <= current_price <= fvg_top
            or abs(current_price - fvg_top) <= threshold
            or abs(current_price - fvg_bottom) <= threshold
        )

    if fvg_type == "Bearish FVG" and fvg_bottom is not None and fvg_top is not None:
        near_bearish_fvg = (
            fvg_bottom <= current_price <= fvg_top
            or abs(current_price - fvg_top) <= threshold
            or abs(current_price - fvg_bottom) <= threshold
        )

    trend_lower = trend.lower()

    if "bullish" in trend_lower:
        in_zone = (
            distance_to_ema20 <= threshold
            or distance_to_support <= threshold
            or near_bullish_fvg
        )

        if in_zone:
            reasons = []
            if distance_to_support <= threshold:
                reasons.append("Support")
            if distance_to_ema20 <= threshold:
                reasons.append("EMA")
            if near_bullish_fvg:
                reasons.append("Bullish FVG")

            return f"Bullish setup: narx kuchli zonada ({'/'.join(reasons)})."

        return "Bullish trend bor, lekin narx entry zonasidan uzoq."

    elif "bearish" in trend_lower:
        in_zone = (
            distance_to_ema20 <= threshold
            or distance_to_resistance <= threshold
            or near_bearish_fvg
        )

        if in_zone:
            reasons = []
            if distance_to_resistance <= threshold:
                reasons.append("Resistance")
            if distance_to_ema20 <= threshold:
                reasons.append("EMA")
            if near_bearish_fvg:
                reasons.append("Bearish FVG")

            return f"Bearish setup: narx kuchli zonada ({'/'.join(reasons)})."

        return "Bearish trend bor, lekin narx entry zonasidan uzoq."

    return "Aniq entry zona topilmadi."


def detect_signal_strength(
    h1_trend: str,
    m15_trend: str,
    rsi_text: str,
    macd_text: str,
    setup_status: str,
    candle_confirmation: str,
) -> str:
    """
    4-QADAM YECHIMI: SIGNAL KUCHINI O'LCHASH.
    Eski bot mantig'i: Agar narx zonada bo'lsa (READY) -> STRONG!
    Agar yaqinlashayotgan bo'lsa (WATCH) -> MEDIUM!
    Kechikuvchi indikatorlarga qarab ballni pasaytirmaymiz.
    """
    if setup_status in [STATUS_READY_BUY, STATUS_READY_SELL]:
        return "STRONG" # Trend bor va narx zonada = Eng kuchli holat!
        
    elif setup_status in [STATUS_BUY_WATCH, STATUS_SELL_WATCH]:
        return "MEDIUM" # Trend bor, narx zonaga kelyapti = O'rta holat
        
    return "WEAK" # Qolgan hamma holatlar = Kuchsiz


def generate_final_signal(
    setup_status: str,
    signal_strength: str,
    candle_confirmation: str,
    risk_reward_ratio,
) -> str:
    """
    3-QADAM YECHIMI: TEPKI BOSISH QOIDASI.
    Eski bot mantig'i: Agar Setup READY va Strength MEDIUM yoki STRONG bo'lsa, signal beradi.
    Risk/Reward skalping uchun 1.0 qilib qo'yildi.
    """
    rr_ok = False
    if risk_reward_ratio != "N/A" and risk_reward_ratio is not None:
        try:
            rr_ok = float(risk_reward_ratio) >= 1.0  # Agressiv bot uchun 1.0 ham yetarli
        except:
            rr_ok = False

    # 1. BUY SIGNAL SHARTLARI
    if setup_status == STATUS_READY_BUY:
        # Eski bot mantig'i: Faqat STRONG yoki MEDIUM qabul qilinadi
        if signal_strength in [SIGNAL_STRONG, SIGNAL_MEDIUM] and rr_ok:
            return FINAL_SIGNAL_BUY

    # 2. SELL SIGNAL SHARTLARI
    elif setup_status == STATUS_READY_SELL:
        # Eski bot mantig'i: Faqat STRONG yoki MEDIUM qabul qilinadi
        if signal_strength in [SIGNAL_STRONG, SIGNAL_MEDIUM] and rr_ok:
            return FINAL_SIGNAL_SELL

    # Agar qoidalar to'la bajarilmasa, hech narsa qilmasdan kutamiz
    return FINAL_SIGNAL_WAIT

def generate_entry_price(
    setup_status: str,
    current_price: float,
    ema20_value: float,
    support: float,
    resistance: float,
    atr_value: float,
    entry_zone_text: str,
):
    """
    Entry ni joriy narxga ko'r-ko'rona bermaydi.
    EMA / support-resistance / FVG yaqinligini hisobga olib
    realistikroq kirish narxini beradi.
    """
    if setup_status not in [STATUS_READY_BUY, STATUS_READY_SELL]:
        return None

    try:
        current_price = float(current_price)
        ema20_value = float(ema20_value)
        support = float(support)
        resistance = float(resistance)
    except (TypeError, ValueError):
        return None

    if atr_value is None or atr_value <= 0:
        atr_value = max(abs(resistance - support) * 0.25, 5.0)

    zone_text = str(entry_zone_text).lower()
    threshold = max(atr_value * 0.40, 2.0)

    if setup_status == STATUS_READY_BUY:
        candidates = [current_price]

        if abs(current_price - ema20_value) <= threshold * 1.5:
            candidates.append(ema20_value)

        if abs(current_price - support) <= threshold * 2.0:
            candidates.append(support + atr_value * 0.15)

        if "bullish fvg" in zone_text:
            candidates.append(current_price - atr_value * 0.20)

        clean_candidates = []
        for price in candidates:
            if price is None:
                continue
            if price <= 0:
                continue
            if price > resistance + atr_value:
                continue
            clean_candidates.append(round(price, 2))

        if not clean_candidates:
            return round(current_price, 2)

        # BUY uchun yaxshiroq narx — iloji boricha pastroq, lekin real zonada
        return round(min(clean_candidates), 2)

    if setup_status == STATUS_READY_SELL:
        candidates = [current_price]

        if abs(current_price - ema20_value) <= threshold * 1.5:
            candidates.append(ema20_value)

        if abs(current_price - resistance) <= threshold * 2.0:
            candidates.append(resistance - atr_value * 0.15)

        if "bearish fvg" in zone_text:
            candidates.append(current_price + atr_value * 0.20)

        clean_candidates = []
        for price in candidates:
            if price is None:
                continue
            if price <= 0:
                continue
            if price < support - atr_value:
                continue
            clean_candidates.append(round(price, 2))

        if not clean_candidates:
            return round(current_price, 2)

        # SELL uchun yaxshiroq narx — iloji boricha yuqoriroq, lekin real zonada
        return round(max(clean_candidates), 2)

    return None

def generate_risk_levels(
    setup_status: str,
    current_price: float,
    suggested_entry: float,
    support: float,
    resistance: float,
    atr_value: float,
    entry_zone_text: str,
):
    """
    SL ni haddan tashqari uzoqqa qo'ymaslik uchun
    structure + ATR buffer + max stop distance cap ishlatadi.
    TP esa structure target va minimal RR floor kombinatsiyasi bilan chiqadi.
    """
    if suggested_entry is None:
        return None, None

    try:
        current_price = float(current_price)
        suggested_entry = float(suggested_entry)
        support = float(support)
        resistance = float(resistance)
    except (TypeError, ValueError):
        return None, None

    if atr_value is None or atr_value <= 0:
        atr_value = max(abs(resistance - support) * 0.25, 5.0)

    zone_text = str(entry_zone_text).lower()

    # Juda uzoq SL chiqib ketmasligi uchun cap (1.8 dan 1.2 ga tushirildi)
    max_stop_distance = max(atr_value * 1.2, 3.0)

    if setup_status == STATUS_READY_BUY:
        # ATR buffer 0.35 dan 0.15 ga tushirildi, SL ixchamroq bo'ladi
        structure_sl = support - atr_value * 0.15
    
        if "bullish fvg" in zone_text:
            structure_sl = max(structure_sl, suggested_entry - atr_value * 0.90)

        capped_sl = suggested_entry - max_stop_distance
        stop_loss = round(max(structure_sl, capped_sl), 2)

        risk = suggested_entry - stop_loss
        if risk <= 0:
            return None, None

        # Juda tor bo'lib qolmasin
        minimum_safe_risk = max(atr_value * 0.60, 2.5)
        if risk < minimum_safe_risk:
            stop_loss = round(suggested_entry - minimum_safe_risk, 2)
            risk = suggested_entry - stop_loss

        structure_tp = resistance - atr_value * 0.15
        rr_floor_tp = suggested_entry + risk * 1.8

        if structure_tp <= suggested_entry:
            take_profit = round(rr_floor_tp, 2)
        else:
            take_profit = round(max(structure_tp, rr_floor_tp), 2)

        return stop_loss, take_profit

    if setup_status == STATUS_READY_SELL:
        structure_sl = resistance + atr_value * 0.35

        if "bearish fvg" in zone_text:
            structure_sl = min(structure_sl, suggested_entry + atr_value * 0.90)

        capped_sl = suggested_entry + max_stop_distance
        stop_loss = round(min(structure_sl, capped_sl), 2)

        risk = stop_loss - suggested_entry
        if risk <= 0:
            return None, None

        # Juda tor bo'lib qolmasin
        minimum_safe_risk = max(atr_value * 0.60, 2.5)
        if risk < minimum_safe_risk:
            stop_loss = round(suggested_entry + minimum_safe_risk, 2)
            risk = stop_loss - suggested_entry

        structure_tp = support + atr_value * 0.15
        rr_floor_tp = suggested_entry - risk * 1.8

        if structure_tp >= suggested_entry:
            take_profit = round(rr_floor_tp, 2)
        else:
            take_profit = round(min(structure_tp, rr_floor_tp), 2)

        return stop_loss, take_profit

    return None, None

def calculate_risk_reward(
    setup_status: str,
    suggested_entry,
    suggested_sl,
    suggested_tp,
):
    if suggested_entry is None or suggested_sl is None or suggested_tp is None:
        return None

    try:
        entry = float(suggested_entry)
        sl    = float(suggested_sl)
        tp    = float(suggested_tp)
    except (TypeError, ValueError):
        return None

    if setup_status == STATUS_READY_BUY:
        risk   = entry - sl
        reward = tp - entry
    elif setup_status == STATUS_READY_SELL:
        risk   = sl - entry
        reward = entry - tp
    else:
        return None

    # Manfiy bo'lsa None qaytaramiz
    if risk <= 0 or reward <= 0:
        return None

    return round(reward / risk, 2)


def generate_alert_message(
    final_signal: str,
    setup_status: str,
    signal_strength: str,
) -> str:
    if final_signal == FINAL_SIGNAL_BUY:
        return "ALERT: Buy signali tayyor."
    elif final_signal == FINAL_SIGNAL_SELL:
        return "ALERT: Sell signali tayyor."
    elif setup_status == STATUS_BUY_WATCH:
        return "ALERT: Buy setup kuzatilyapti."
    elif setup_status == STATUS_SELL_WATCH:
        return "ALERT: Sell setup kuzatilyapti."
    elif setup_status in [STATUS_READY_BUY, STATUS_READY_SELL]:
        return "ALERT: Setup bor, lekin risk/reward yoki tasdiq yetarli emas."
    else:
        return "ALERT: Hozircha signal kuchsiz."


def generate_reason(
    h1_trend: str,
    m15_trend: str,
    rsi_text: str,
    macd_text: str,
    price_location: str,
    entry_zone_text: str,
    setup_status: str,
    final_signal: str,
    risk_reward_ratio,
    candle_confirmation: str,
    signal_strength: str,
) -> str:
    """
    4-QADAM YECHIMI: TELEGRAM XABARLARINI TOZALASH.
    Bot endi sizga nima uchun kirmayotganini aniq, adashtirmasdan aytadi.
    """
    if final_signal in [FINAL_SIGNAL_BUY, FINAL_SIGNAL_SELL]:
        return f"{final_signal} tasdiqlandi. H1+M15 trend bir tomonda va narx aniq entry zonasida."

    reasons = []

    if setup_status not in [STATUS_READY_BUY, STATUS_READY_SELL]:
        reasons.append(f"Setup hali {setup_status} rejimida (narx zonaga kelishi kutilmoqda)")

    rr_ok = False
    if risk_reward_ratio is not None and risk_reward_ratio != "N/A":
        try:
            rr_ok = float(risk_reward_ratio) >= 1.0
        except Exception:
            rr_ok = False

    if setup_status in [STATUS_READY_BUY, STATUS_READY_SELL] and not rr_ok:
        reasons.append(f"Risk/Reward 1.0 dan past ({risk_reward_ratio})")

    if not reasons:
        return "WAIT: Bozorda qulay vaziyat kutilmoqda."

    return "WAIT sababi: " + ", ".join(reasons) + "."


def detect_candle_confirmation(df) -> str:
    """
    PRO YONDASHUV: Liquidity Sweep (Pin bar) va Momentum (Engulfing) tasdiqlari.
    Banklar stop-losslarni urib qaytgandagi izlarni qidiradi.
    """
    if len(df) < 3:
        return "No clear candle confirmation"

    last = df.iloc[-1]
    prev = df.iloc[-2]

    body_size = abs(last["close"] - last["open"])
    total_range = last["high"] - last["low"]
    
    if total_range == 0:
        return "No clear candle confirmation"

    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]

    # 1. LIQUIDITY SWEEP (Pin Bar / Hammer)
    if lower_wick > (total_range * 0.6) and body_size < (total_range * 0.3):
        return "Strong Bullish confirmation (Liquidity Sweep / Pin Bar)"

    if upper_wick > (total_range * 0.6) and body_size < (total_range * 0.3):
        return "Strong Bearish confirmation (Liquidity Sweep / Pin Bar)"

    # 2. ENGULFING (Yutib yuborish)
    if last["close"] > last["open"] and prev["close"] < prev["open"] and last["close"] >= prev["open"] and last["open"] <= prev["close"]:
        return "Bullish candle confirmation (Engulfing)"

    if last["close"] < last["open"] and prev["close"] > prev["open"] and last["close"] <= prev["open"] and last["open"] >= prev["close"]:
        return "Bearish candle confirmation (Engulfing)"

    # 3. Oddiy momentum tasdiqlari
    if last["close"] > last["open"] and last["close"] > prev["high"]:
        return "Bullish candle confirmation"

    if last["close"] < last["open"] and last["close"] < prev["low"]:
        return "Bearish candle confirmation"
        
    if last["close"] > last["open"]:
        return "Weak bullish candle"

    if last["close"] < last["open"]:
        return "Weak bearish candle"

    return "No clear candle confirmation"

def find_latest_fvg(df: pd.DataFrame):
    """
    PRO YONDASHUV: Fair Value Gap (FVG) / Imbalance ni aniqlash.
    Oxirgi 20 ta sham ichidan eng so'nggi FVG bo'shlig'ini topadi.
    """
    if len(df) < 25:
        return "No FVG", None, None
        
    for i in range(1, 20):
        idx1 = -(i+2) # 1-sham
        idx3 = -i     # 3-sham
        
        c1_high = df['high'].iloc[idx1]
        c1_low = df['low'].iloc[idx1]
        c3_high = df['high'].iloc[idx3]
        c3_low = df['low'].iloc[idx3]
        
        # Bullish FVG (Yashil impuls bo'shlig'i)
        if c3_low > c1_high:
            return "Bullish FVG", c1_high, c3_low
            
        # Bearish FVG (Qizil impuls bo'shlig'i)
        if c3_high < c1_low:
            return "Bearish FVG", c3_high, c1_low
            
    return "No FVG", None, None



def analyze_volume(df: pd.DataFrame) -> str:
    """
    Volume tahlili — sham kuchini tasdiqlaydi.

    Mantiq:
      Oxirgi sham volume si oldingi 20 ta shamning
      o'rtacha volume sidan katta bo'lsa — kuchli sham.

      Kuchli bullish sham + yuqori volume = ishonchli BUY
      Kuchli bearish sham + yuqori volume = ishonchli SELL
    """
    if "tick_volume" not in df.columns or len(df) < 21:
        return "VOLUME: Ma'lumot yetarli emas"

    last        = df.iloc[-1]
    avg_volume  = df["tick_volume"].iloc[-21:-1].mean()
    last_volume = last["tick_volume"]

    is_high_volume = last_volume > avg_volume * 1.3
    is_bullish     = last["close"] > last["open"]
    is_bearish     = last["close"] < last["open"]

    if is_high_volume and is_bullish:
        return "VOLUME: Yuqori — Bullish tasdiqlandi"
    elif is_high_volume and is_bearish:
        return "VOLUME: Yuqori — Bearish tasdiqlandi"
    elif is_high_volume:
        return "VOLUME: Yuqori — Yo'nalish noaniq"
    else:
        return "VOLUME: Past — Sham kuchsiz"
    

def get_session_status() -> str:
    """
    Sessiya filtri — faqat kuchli sessiyalarda signal.

    O'zbekiston vaqti (UTC+5) bo'yicha:
      London sessiyasi: 12:00 - 17:00
      Overlap:          17:00 - 20:00
      New York:         20:00 - 23:00
      Asia:             03:00 - 12:00
    """
    now = datetime.now(ZoneInfo(TIMEZONE))
    hour = now.hour

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


def is_good_session() -> bool:
    """
    Agressiv bot uchun barcha ochiq sessiyalarda (Osiyo, London, NY) 
    True qaytaradi. Faqat bozor yopiq (weekend) bo'lsa False qaytaradi.
    """
    status = get_session_status()
    # Faqat bozor butunlay yopiq bo'lsa (CLOSED) bloklaymiz
    return "CLOSED" not in status



def add_stochastic_rsi(df: pd.DataFrame, period: int = 14, smooth: int = 3) -> pd.DataFrame:
    """
    Stochastic RSI — RSI dan aniqroq signal.

    Oddiy RSI: 70 dan yuqori = overbought (lekin trend paytida
    uzoq vaqt 70 da qolishi mumkin — yolg'on signal).

    Stochastic RSI: RSI ning o'zini stochastic qiladi.
      0-20  = Oversold (BUY uchun kuchli signal)
      80-100 = Overbought (SELL uchun kuchli signal)

    Pro treyderlar RSI + StochRSI birgalikda ishlatadi.
    """
    if "RSI" not in df.columns:
        return df

    rsi        = df["RSI"]
    rsi_min    = rsi.rolling(window=period).min()
    rsi_max    = rsi.rolling(window=period).max()
    rsi_range  = rsi_max - rsi_min

    # 0 ga bo'lishdan saqlash
    stoch_rsi  = (rsi - rsi_min) / rsi_range.replace(0, float("inf"))

    # K va D chiziqlari (smoothing)
    df["StochRSI_K"] = stoch_rsi.rolling(window=smooth).mean() * 100
    df["StochRSI_D"] = df["StochRSI_K"].rolling(window=smooth).mean()

    return df


def interpret_stochastic_rsi(df: pd.DataFrame) -> str:
    """
    Stochastic RSI holatini matn sifatida qaytaradi.
    """
    if "StochRSI_K" not in df.columns:
        return "StochRSI: Hisoblanmadi"

    k = df["StochRSI_K"].iloc[-1]
    d = df["StochRSI_D"].iloc[-1]

    if k < 20 and d < 20:
        return "StochRSI: Oversold — Kuchli BUY signal"
    elif k > 80 and d > 80:
        return "StochRSI: Overbought — Kuchli SELL signal"
    elif k > d and k < 50:
        return "StochRSI: Bullish kesishma — BUY imkoniyati"
    elif k < d and k > 50:
        return "StochRSI: Bearish kesishma — SELL imkoniyati"
    else:
        return "StochRSI: Neytral zona"
    

def detect_rsi_divergence(df: pd.DataFrame) -> str:
    """
    Professionalroq RSI divergence:
    - price pivot high / low topadi
    - RSI pivot high / low topadi
    - oxirgi 2 ta muhim pivotni solishtiradi
    - bullish / bearish divergence ni qaytaradi
    """
    if df is None or len(df) < 25:
        return "Divergence: Aniqlik uchun data yetarli emas"

    if "RSI" not in df.columns:
        return "Divergence: RSI topilmadi"

    recent = df.tail(80).copy().reset_index(drop=True)
    if len(recent) < 25:
        return "Divergence: Aniqlik uchun data yetarli emas"

    recent["range"] = recent["high"] - recent["low"]
    avg_range = recent["range"].tail(20).mean()

    if pd.isna(avg_range) or avg_range <= 0:
        avg_range = 5.0

    pivot_buffer = max(avg_range * 0.10, 0.50)

    price_low_pivots = []
    price_high_pivots = []

    for i in range(2, len(recent) - 2):
        low_i = float(recent.iloc[i]["low"])
        high_i = float(recent.iloc[i]["high"])

        prev_low_1 = float(recent.iloc[i - 1]["low"])
        prev_low_2 = float(recent.iloc[i - 2]["low"])
        next_low_1 = float(recent.iloc[i + 1]["low"])
        next_low_2 = float(recent.iloc[i + 2]["low"])

        prev_high_1 = float(recent.iloc[i - 1]["high"])
        prev_high_2 = float(recent.iloc[i - 2]["high"])
        next_high_1 = float(recent.iloc[i + 1]["high"])
        next_high_2 = float(recent.iloc[i + 2]["high"])

        if (
            low_i <= prev_low_1
            and low_i <= prev_low_2
            and low_i <= next_low_1
            and low_i <= next_low_2
        ):
            price_low_pivots.append({
                "idx": i,
                "price": round(low_i, 2),
                "rsi": float(recent.iloc[i]["RSI"]),
            })

        if (
            high_i >= prev_high_1
            and high_i >= prev_high_2
            and high_i >= next_high_1
            and high_i >= next_high_2
        ):
            price_high_pivots.append({
                "idx": i,
                "price": round(high_i, 2),
                "rsi": float(recent.iloc[i]["RSI"]),
            })

    if len(price_low_pivots) >= 2:
        prev_low = price_low_pivots[-2]
        last_low = price_low_pivots[-1]

        price_made_lower_low = last_low["price"] < prev_low["price"] - pivot_buffer
        rsi_made_higher_low = last_low["rsi"] > prev_low["rsi"] + 1.5

        if price_made_lower_low and rsi_made_higher_low:
            return (
                f"Divergence: Bullish divergence - price LL "
                f"({prev_low['price']:.2f} -> {last_low['price']:.2f}), "
                f"RSI HL ({prev_low['rsi']:.1f} -> {last_low['rsi']:.1f})"
            )

    if len(price_high_pivots) >= 2:
        prev_high = price_high_pivots[-2]
        last_high = price_high_pivots[-1]

        price_made_higher_high = last_high["price"] > prev_high["price"] + pivot_buffer
        rsi_made_lower_high = last_high["rsi"] < prev_high["rsi"] - 1.5

        if price_made_higher_high and rsi_made_lower_high:
            return (
                f"Divergence: Bearish divergence - price HH "
                f"({prev_high['price']:.2f} -> {last_high['price']:.2f}), "
                f"RSI LH ({prev_high['rsi']:.1f} -> {last_high['rsi']:.1f})"
            )

    # hidden divergence (secondary context)
    if len(price_low_pivots) >= 2:
        prev_low = price_low_pivots[-2]
        last_low = price_low_pivots[-1]

        hidden_bullish = (
            last_low["price"] > prev_low["price"] + pivot_buffer
            and last_low["rsi"] < prev_low["rsi"] - 1.5
        )

        if hidden_bullish:
            return (
                f"Divergence: Hidden bullish divergence - price HL "
                f"({prev_low['price']:.2f} -> {last_low['price']:.2f}), "
                f"RSI LL ({prev_low['rsi']:.1f} -> {last_low['rsi']:.1f})"
            )

    if len(price_high_pivots) >= 2:
        prev_high = price_high_pivots[-2]
        last_high = price_high_pivots[-1]

        hidden_bearish = (
            last_high["price"] < prev_high["price"] - pivot_buffer
            and last_high["rsi"] > prev_high["rsi"] + 1.5
        )

        if hidden_bearish:
            return (
                f"Divergence: Hidden bearish divergence - price LH "
                f"({prev_high['price']:.2f} -> {last_high['price']:.2f}), "
                f"RSI HH ({prev_high['rsi']:.1f} -> {last_high['rsi']:.1f})"
            )

    return "Divergence: Yo'q"

def calculate_multi_tp(
    setup_status: str,
    entry: float,
    sl: float,
    atr_value: float,
):
    """
    TP1, TP2, TP3 hisoblash — Partial Profit strategiyasi.

    Pro treyderlar bir pozitsiyani 3 qismga bo'ladi:
      TP1 (33% lot) — RR 1:1.5 — Tez foyda, stress kamaytirish
      TP2 (33% lot) — RR 1:2.5 — Asosiy foyda
      TP3 (34% lot) — RR 1:4.0 — Katta harakat uchun

    Matematik:
      risk = |entry - sl|
      TP1  = entry + risk * 1.5  (BUY uchun)
      TP2  = entry + risk * 2.5
      TP3  = entry + risk * 4.0
    """
    if entry is None or sl is None:
        return None, None, None

    try:
        entry = float(entry)
        sl    = float(sl)
    except (TypeError, ValueError):
        return None, None, None

    risk = abs(entry - sl)
    if risk <= 0:
        return None, None, None

    if setup_status == STATUS_READY_BUY:
        tp1 = round(entry + risk * 1.5, 2)
        tp2 = round(entry + risk * 2.5, 2)
        tp3 = round(entry + risk * 4.0, 2)

    elif setup_status == STATUS_READY_SELL:
        tp1 = round(entry - risk * 1.5, 2)
        tp2 = round(entry - risk * 2.5, 2)
        tp3 = round(entry - risk * 4.0, 2)

    else:
        return None, None, None

    return tp1, tp2, tp3


def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    entry: float,
    sl: float,
    tick_value: float = 1.0,
    lot_step: float = 0.01,
):
    """
    Position sizing — hisobdagi % ga qarab lot hisoblash.

    Pro treyderlar har bir tradega hisobning 1-2% dan ko'p
    risk qilmaydi. Bu kapitalning uzoq muddatda saqlanishini
    ta'minlaydi.

    Matematik:
      risk_amount = balance * risk_percent / 100
      sl_pips     = |entry - sl|
      lot_size    = risk_amount / (sl_pips * tick_value)

    Misol:
      balance     = 10000$
      risk        = 1%  → 100$
      SL masofasi = 10 pip
      tick_value  = 1$
      lot_size    = 100 / (10 * 1) = 1.0 lot
    """
    if entry is None or sl is None:
        return 0.01

    try:
        risk_amount = account_balance * risk_percent / 100
        sl_distance = abs(entry - sl)

        if sl_distance <= 0 or tick_value <= 0:
            return 0.01

        raw_lot = risk_amount / (sl_distance * tick_value)

        # Lot step ga yaxlitlash (0.01, 0.02, ...)
        lot = round(raw_lot / lot_step) * lot_step
        lot = max(0.01, min(lot, 10.0))  # Min 0.01, Max 10.0

        return round(lot, 2)

    except Exception:
        return 0.01


def calculate_breakeven_level(
    setup_status: str,
    entry: float,
    tp1: float,
    current_price: float,
):
    """
    Breakeven SL — TP1 ga yetganda SL ni entry ga ko'chirish.

    Mantiq:
      Narx TP1 ga yetdi → SL ni entry ga ko'chiramiz
      Natija: eng yomon holatda ham zarar yo'q (breakeven)

    Bu pro treyderlarning eng muhim risk management usuli.
    """
    if entry is None or tp1 is None:
        return None, False

    try:
        entry         = float(entry)
        tp1           = float(tp1)
        current_price = float(current_price)
    except (TypeError, ValueError):
        return None, False

    if setup_status == STATUS_READY_BUY:
        tp1_reached = current_price >= tp1
        if tp1_reached:
            return round(entry + 2, 2), True  # Entry + 2 pip buffer
        return None, False

    elif setup_status == STATUS_READY_SELL:
        tp1_reached = current_price <= tp1
        if tp1_reached:
            return round(entry - 2, 2), True  # Entry - 2 pip buffer
        return None, False

    return None, False


def calculate_trailing_stop(
    setup_status: str,
    entry: float,
    current_price: float,
    atr_value: float,
    trail_multiplier: float = 2.0,
):
    """
    Trailing Stop Loss — narx harakatlanishi bilan SL ham ko'chadi.

    ATR asosida trailing:
      Trail distance = ATR * multiplier (default 2.0)

      BUY  → trailing_sl = current_price - (ATR * 2)
      SELL → trailing_sl = current_price + (ATR * 2)

    Bu usul trenddagi katta harakatlardan foyda olish imkonini beradi
    va ayni vaqtda qaytish bo'lsa profitni himoya qiladi.
    """
    if entry is None or atr_value is None or atr_value <= 0:
        return None

    try:
        entry         = float(entry)
        current_price = float(current_price)
        trail_dist    = atr_value * trail_multiplier
    except (TypeError, ValueError):
        return None

    if setup_status == STATUS_READY_BUY:
        # Faqat narx entrydan yuqorida bo'lsa trailing aktiv
        if current_price > entry:
            return round(current_price - trail_dist, 2)
        return None

    elif setup_status == STATUS_READY_SELL:
        # Faqat narx entrydan pastda bo'lsa trailing aktiv
        if current_price < entry:
            return round(current_price + trail_dist, 2)
        return None

    return None


def check_market_structure(df: pd.DataFrame) -> str:
    """
    Professionalroq market structure:
    - pivot high / pivot low topadi
    - HH / HL va LH / LL ni tekshiradi
    - BOS (break of structure) ni aniqlaydi
    - mixed / ranging holatni alohida qaytaradi
    """
    if df is None or len(df) < 20:
        return "STRUCTURE: Aniqlik uchun data yetarli emas"

    recent = df.tail(70).copy().reset_index(drop=True)
    if len(recent) < 20:
        return "STRUCTURE: Aniqlik uchun data yetarli emas"

    recent["range"] = recent["high"] - recent["low"]
    avg_range = recent["range"].tail(20).mean()

    if pd.isna(avg_range) or avg_range <= 0:
        avg_range = 5.0

    break_buffer = max(avg_range * 0.15, 0.80)
    current_close = float(recent["close"].iloc[-1])

    swing_highs = []
    swing_lows = []

    for i in range(2, len(recent) - 2):
        hi = float(recent.iloc[i]["high"])
        lo = float(recent.iloc[i]["low"])

        if (
            hi >= float(recent.iloc[i - 1]["high"])
            and hi >= float(recent.iloc[i - 2]["high"])
            and hi >= float(recent.iloc[i + 1]["high"])
            and hi >= float(recent.iloc[i + 2]["high"])
        ):
            swing_highs.append((i, round(hi, 2)))

        if (
            lo <= float(recent.iloc[i - 1]["low"])
            and lo <= float(recent.iloc[i - 2]["low"])
            and lo <= float(recent.iloc[i + 1]["low"])
            and lo <= float(recent.iloc[i + 2]["low"])
        ):
            swing_lows.append((i, round(lo, 2)))

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "STRUCTURE: Swinglar yetarli emas"

    last_high_idx, last_high = swing_highs[-1]
    prev_high_idx, prev_high = swing_highs[-2]

    last_low_idx, last_low = swing_lows[-1]
    prev_low_idx, prev_low = swing_lows[-2]

    hh = last_high > prev_high + break_buffer
    lh = last_high < prev_high - break_buffer
    hl = last_low > prev_low + break_buffer
    ll = last_low < prev_low - break_buffer

    bullish_bos = current_close > prev_high + break_buffer
    bearish_bos = current_close < prev_low - break_buffer

    if hh and hl:
        if bullish_bos:
            return (
                f"STRUCTURE: Bullish BOS - HH + HL "
                f"(prevH {prev_high:.2f} -> lastH {last_high:.2f}, "
                f"prevL {prev_low:.2f} -> lastL {last_low:.2f})"
            )
        return (
            f"STRUCTURE: Bullish - HH + HL "
            f"(Trend yuqoriga, BOS tasdiqi hali kuchsiz)"
        )

    if lh and ll:
        if bearish_bos:
            return (
                f"STRUCTURE: Bearish BOS - LH + LL "
                f"(prevH {prev_high:.2f} -> lastH {last_high:.2f}, "
                f"prevL {prev_low:.2f} -> lastL {last_low:.2f})"
            )
        return (
            f"STRUCTURE: Bearish - LH + LL "
            f"(Trend pastga, BOS tasdiqi hali kuchsiz)"
        )

    # Transitional / mixed states
    if hh and ll:
        return (
            f"STRUCTURE: Volatile / Expansion - HH va LL birga mavjud, "
            f"aniq trend yo'q"
        )

    if lh and hl:
        return (
            f"STRUCTURE: Ranging / Compression - LH va HL, "
            f"breakout kutilmoqda"
        )

    # Close-based fallback
    structure_high = max(prev_high, last_high)
    structure_low = min(prev_low, last_low)

    if current_close > structure_high + break_buffer:
        return (
            f"STRUCTURE: Bullish continuation - narx swing high ustida"
        )

    if current_close < structure_low - break_buffer:
        return (
            f"STRUCTURE: Bearish continuation - narx swing low ostida"
        )

    return "STRUCTURE: Mixed - aniq HH/HL yoki LH/LL yo'q"

def detect_order_block(df: pd.DataFrame, trend: str) -> str:
    """
    Order Block aniqlash — Banklar kirgan zona.

    Order Block = kuchli impuls harakatidan oldingi so'nggi
    teskari yo'nalishli sham. Bu yerdan narx qaytishi mumkin.

    Bullish OB: Pastga harakatdan oldingi oxirgi bearish sham
    Bearish OB: Yuqoriga harakatdan oldingi oxirgi bullish sham

    Pro treyderlar bu zonani entry uchun ishlatadi.
    """
    if len(df) < 10:
        return "OB: Yetarli ma'lumot yo'q"

    current_price = df["close"].iloc[-1]

    if "Bullish" in trend:
        # Oxirgi 10 ta shamdan bearish shamlarni qidirish
        for i in range(len(df) - 2, max(len(df) - 15, 0), -1):
            candle = df.iloc[i]
            if candle["close"] < candle["open"]:  # Bearish sham
                ob_high = candle["high"]
                ob_low  = candle["low"]
                if ob_low <= current_price <= ob_high:
                    return f"OB: Bullish Order Block zonasida ({ob_low:.2f} - {ob_high:.2f})"
                elif current_price > ob_high:
                    return f"OB: Bullish OB tepasida — narx ustida ({ob_high:.2f})"
                break

    elif "Bearish" in trend:
        for i in range(len(df) - 2, max(len(df) - 15, 0), -1):
            candle = df.iloc[i]
            if candle["close"] > candle["open"]:  # Bullish sham
                ob_high = candle["high"]
                ob_low  = candle["low"]
                if ob_low <= current_price <= ob_high:
                    return f"OB: Bearish Order Block zonasida ({ob_low:.2f} - {ob_high:.2f})"
                elif current_price < ob_low:
                    return f"OB: Bearish OB pastida — narx ostida ({ob_low:.2f})"
                break

    return "OB: Aniq Order Block topilmadi"


def detect_liquidity_zones(df: pd.DataFrame) -> str:
    """
    Professionalroq liquidity zones:
    - equal highs / equal lows clusterlarini qidiradi
    - pivot asosida ishlaydi
    - narxga eng relevant buy-side va sell-side liquidity ni qaytaradi
    """
    if df is None or len(df) < 20:
        return "LIQUIDITY: Aniqlik uchun data yetarli emas"

    recent = df.tail(60).copy().reset_index(drop=True)
    if len(recent) < 20:
        return "LIQUIDITY: Aniqlik uchun data yetarli emas"

    recent["range"] = recent["high"] - recent["low"]
    avg_range = recent["range"].tail(20).mean()

    if pd.isna(avg_range) or avg_range <= 0:
        avg_range = 5.0

    current_price = float(recent["close"].iloc[-1])
    cluster_threshold = max(avg_range * 0.18, 0.80)

    swing_highs = []
    swing_lows = []

    for i in range(2, len(recent) - 2):
        high_i = float(recent.iloc[i]["high"])
        low_i = float(recent.iloc[i]["low"])

        prev_high_1 = float(recent.iloc[i - 1]["high"])
        prev_high_2 = float(recent.iloc[i - 2]["high"])
        next_high_1 = float(recent.iloc[i + 1]["high"])
        next_high_2 = float(recent.iloc[i + 2]["high"])

        prev_low_1 = float(recent.iloc[i - 1]["low"])
        prev_low_2 = float(recent.iloc[i - 2]["low"])
        next_low_1 = float(recent.iloc[i + 1]["low"])
        next_low_2 = float(recent.iloc[i + 2]["low"])

        if high_i >= prev_high_1 and high_i >= prev_high_2 and high_i >= next_high_1 and high_i >= next_high_2:
            swing_highs.append(round(high_i, 2))

        if low_i <= prev_low_1 and low_i <= prev_low_2 and low_i <= next_low_1 and low_i <= next_low_2:
            swing_lows.append(round(low_i, 2))

    def build_clusters(levels, side_name: str):
        if not levels:
            return []

        levels = sorted(levels)
        clusters = [[levels[0]]]

        for lvl in levels[1:]:
            current_cluster = clusters[-1]
            current_mean = sum(current_cluster) / len(current_cluster)

            if abs(lvl - current_mean) <= cluster_threshold:
                current_cluster.append(lvl)
            else:
                clusters.append([lvl])

        result = []
        for cluster in clusters:
            if len(cluster) < 2:
                continue

            level = round(sum(cluster) / len(cluster), 2)
            touches = len(cluster)
            distance = abs(current_price - level)

            if side_name == "buy-side":
                if level <= current_price:
                    continue

                if (level - current_price) <= cluster_threshold * 1.2:
                    status = "narxga juda yaqin, tepaga liquidity sweep xavfi yuqori"
                else:
                    status = "narx ustida, buy-side liquidity mavjud"

            else:  # sell-side
                if level >= current_price:
                    continue

                if (current_price - level) <= cluster_threshold * 1.2:
                    status = "narxga juda yaqin, pastga liquidity sweep xavfi yuqori"
                else:
                    status = "narx ostida, sell-side liquidity mavjud"

            result.append({
                "side": side_name,
                "level": level,
                "touches": touches,
                "distance": round(distance, 2),
                "status": status,
            })

        return result

    buy_side_clusters = build_clusters(swing_highs, "buy-side")
    sell_side_clusters = build_clusters(swing_lows, "sell-side")

    if not buy_side_clusters and not sell_side_clusters:
        return "LIQUIDITY: Aniq equal highs / equal lows topilmadi"

    buy_side_clusters = sorted(buy_side_clusters, key=lambda x: (x["distance"], -x["touches"]))
    sell_side_clusters = sorted(sell_side_clusters, key=lambda x: (x["distance"], -x["touches"]))

    parts = []

    if sell_side_clusters:
        best_sell = sell_side_clusters[0]
        parts.append(
            f"Sell-side liquidity {best_sell['level']:.2f} atrofida "
            f"({best_sell['touches']} touch) — {best_sell['status']}"
        )

    if buy_side_clusters:
        best_buy = buy_side_clusters[0]
        parts.append(
            f"Buy-side liquidity {best_buy['level']:.2f} atrofida "
            f"({best_buy['touches']} touch) — {best_buy['status']}"
        )

    return "LIQUIDITY: " + " | ".join(parts)


def detect_fair_value_gap_advanced(df: pd.DataFrame) -> dict:
    """
    Professionalroq FVG:
    - 3 shamli imbalance
    - middle candle impulsive bo'lishi kerak
    - gap juda kichik bo'lmasligi kerak
    - full fill bo'lgan gaplar bekor qilinadi
    - recent va hali relevant gap qaytariladi
    """
    default_result = {
        "found": False,
        "direction": "NONE",
        "type": "No FVG",
        "top": None,
        "bottom": None,
        "mid": None,
        "size": 0.0,
        "status": "none",
        "age": None,
        "text": "FVG: Topilmadi",
    }

    if df is None or len(df) < 10:
        return default_result

    recent = df.tail(40).copy().reset_index(drop=True)
    if len(recent) < 10:
        return default_result

    recent["range"] = recent["high"] - recent["low"]
    avg_range = recent["range"].tail(20).mean()

    if pd.isna(avg_range) or avg_range <= 0:
        avg_range = 5.0

    current_price = float(recent["close"].iloc[-1])
    min_gap_size = max(avg_range * 0.12, 0.80)

    candidates = []

    for i in range(2, len(recent)):
        c1 = recent.iloc[i - 2]
        c2 = recent.iloc[i - 1]
        c3 = recent.iloc[i]

        middle_range = float(c2["high"] - c2["low"])
        middle_body = abs(float(c2["close"] - c2["open"]))

        if middle_range <= 0:
            continue

        impulsive_middle = middle_body >= middle_range * 0.45
        if not impulsive_middle:
            continue

        after = recent.iloc[i + 1:].copy()

        # Bearish FVG: candle1 low > candle3 high
        if float(c1["low"]) > float(c3["high"]):
            gap_top = float(c1["low"])
            gap_bottom = float(c3["high"])
            gap_size = gap_top - gap_bottom

            if gap_size >= min_gap_size:
                fully_filled = False
                partially_filled = False

                if not after.empty:
                    if (after["high"] >= gap_top).any():
                        fully_filled = True
                    elif (after["high"] > gap_bottom).any():
                        partially_filled = True

                if not fully_filled:
                    mid = round((gap_bottom + gap_top) / 2, 2)
                    age = len(recent) - 1 - i
                    distance = abs(current_price - mid)

                    candidates.append({
                        "found": True,
                        "direction": "BEARISH",
                        "type": "Bearish FVG",
                        "top": round(gap_top, 2),
                        "bottom": round(gap_bottom, 2),
                        "mid": mid,
                        "size": round(gap_size, 2),
                        "status": "partial" if partially_filled else "open",
                        "age": age,
                        "distance": round(distance, 2),
                    })

    if not candidates:
        return default_result

    # Eng recent va eng relevant FVG ni tanlaymiz
    candidates = sorted(
        candidates,
        key=lambda x: (x["age"], x["distance"], -x["size"])
    )
    best = candidates[0]

    state_text = "aktiv" if best["status"] == "open" else "qisman to'ldirilgan"

    if best["direction"] == "BULLISH":
        best["text"] = (
            f"FVG: Bullish FVG ({best['bottom']:.2f} - {best['top']:.2f}) "
            f"[{state_text}]"
        )
    else:
        best["text"] = (
            f"FVG: Bearish FVG ({best['bottom']:.2f} - {best['top']:.2f}) "
            f"[{state_text}]"
        )

    return best


def detect_breaker_block(df: pd.DataFrame, trend_text: str) -> str:
    """
    Professionalroq breaker block:
    - old zone invalidated bo'lishi kerak
    - displacement bilan break bo'lishi kerak
    - keyin retest / near-retest holati tekshiriladi
    """
    if df is None or len(df) < 20:
        return "BREAKER: Topilmadi"

    recent = df.tail(50).copy().reset_index(drop=True)
    if len(recent) < 20:
        return "BREAKER: Topilmadi"

    recent["range"] = recent["high"] - recent["low"]
    avg_range = recent["range"].tail(20).mean()

    if pd.isna(avg_range) or avg_range <= 0:
        avg_range = 5.0

    current_price = float(recent["close"].iloc[-1])
    trend_lower = str(trend_text).lower()

    break_threshold = max(avg_range * 0.20, 1.0)
    proximity_threshold = max(avg_range * 0.35, 1.5)

    candidates = []

    # Bullish breaker:
    # old bearish candle / small supply zone buzilib, keyin support sifatida qaraladi
    if "bull" in trend_lower:
        for i in range(3, len(recent) - 5):
            base = recent.iloc[i]
            before = recent.iloc[max(0, i - 3):i].copy()
            after = recent.iloc[i + 1:i + 6].copy()

            if before.empty or after.empty:
                continue

            base_bearish = float(base["close"]) < float(base["open"])
            if not base_bearish:
                continue

            zone_low = min(float(base["open"]), float(base["close"]))
            zone_high = max(float(base["open"]), float(base["close"]))
            pre_swing_high = float(before["high"].max())

            broke_up = float(after["close"].max()) > max(zone_high, pre_swing_high) + break_threshold
            if not broke_up:
                continue

            retest_hit = (after["low"] <= zone_high + proximity_threshold).any()

            if zone_low <= current_price <= zone_high:
                status = "narx bullish breaker ichida"
            elif abs(current_price - zone_high) <= proximity_threshold:
                status = "bullish breaker yaqinida"
            elif retest_hit:
                status = "bullish breaker retest qilinib bo'lgan"
            else:
                status = "break bo'lgan, retest kutilmoqda"

            age = len(recent) - 1 - i
            distance = abs(current_price - ((zone_low + zone_high) / 2))

            candidates.append({
                "type": "bullish",
                "low": round(zone_low, 2),
                "high": round(zone_high, 2),
                "age": age,
                "distance": round(distance, 2),
                "status": status,
            })

    # Bearish breaker:
    # old bullish candle / demand zone buzilib, keyin resistance sifatida qaraladi
    elif "bear" in trend_lower:
        for i in range(3, len(recent) - 5):
            base = recent.iloc[i]
            before = recent.iloc[max(0, i - 3):i].copy()
            after = recent.iloc[i + 1:i + 6].copy()

            if before.empty or after.empty:
                continue

            base_bullish = float(base["close"]) > float(base["open"])
            if not base_bullish:
                continue

            zone_low = min(float(base["open"]), float(base["close"]))
            zone_high = max(float(base["open"]), float(base["close"]))
            pre_swing_low = float(before["low"].min())

            broke_down = float(after["close"].min()) < min(zone_low, pre_swing_low) - break_threshold
            if not broke_down:
                continue

            retest_hit = (after["high"] >= zone_low - proximity_threshold).any()

            if zone_low <= current_price <= zone_high:
                status = "narx bearish breaker ichida"
            elif abs(current_price - zone_low) <= proximity_threshold:
                status = "bearish breaker yaqinida"
            elif retest_hit:
                status = "bearish breaker retest qilinib bo'lgan"
            else:
                status = "break bo'lgan, retest kutilmoqda"

            age = len(recent) - 1 - i
            distance = abs(current_price - ((zone_low + zone_high) / 2))

            candidates.append({
                "type": "bearish",
                "low": round(zone_low, 2),
                "high": round(zone_high, 2),
                "age": age,
                "distance": round(distance, 2),
                "status": status,
            })

    if not candidates:
        return "BREAKER: Topilmadi"

    candidates = sorted(candidates, key=lambda x: (x["age"], x["distance"]))
    best = candidates[0]

    if best["type"] == "bullish":
        return (
            f"BREAKER: Bullish breaker ({best['low']:.2f} - {best['high']:.2f}) — "
            f"{best['status']}"
        )

    return (
        f"BREAKER: Bearish breaker ({best['low']:.2f} - {best['high']:.2f}) — "
        f"{best['status']}"
    )


def detect_imbalance_fill(df: pd.DataFrame) -> str:
    """
    Imbalance to'ldirish tekshiruvi.

    Narx FVG ni to'ldirmoqdami?
    Bu muhim — to'ldirgandan keyin trend davom etishi mumkin.

    To'liq to'ldirildi  → Trend kuchsizlashishi mumkin
    Qisman to'ldirildi  → Hali imkoniyat bor
    To'ldirilmadi       → Kuchli harakat kutilmoqda
    """
    fvg = detect_fair_value_gap_advanced(df)

    fvg_type = str(fvg.get("type", "")).strip()
    fvg_direction = str(fvg.get("direction", "")).strip().upper()
    fvg_found = bool(fvg.get("found", False))

    current = df["close"].iloc[-1]

    if fvg_type == "Bullish FVG" or fvg_direction == "BULLISH":
        if current >= fvg["top"]:
            return "IMBALANCE: Bullish FVG to'liq to'ldirildi — Ehtiyot bo'ling"
        elif current >= fvg["bottom"]:
            fill_pct = (current - fvg["bottom"]) / (fvg["top"] - fvg["bottom"]) * 100
            return f"IMBALANCE: Bullish FVG {fill_pct:.0f}% to'ldirildi"
        else:
            return "IMBALANCE: Bullish FVG to'ldirilmagan — Narx qaytishi kutilmoqda"

    elif fvg_type == "Bearish FVG" or fvg_direction == "BEARISH":
        if current <= fvg["bottom"]:
            return "IMBALANCE: Bearish FVG to'liq to'ldirildi — Ehtiyot bo'ling"
        elif current <= fvg["top"]:
            fill_pct = (fvg["top"] - current) / (fvg["top"] - fvg["bottom"]) * 100
            return f"IMBALANCE: Bearish FVG {fill_pct:.0f}% to'ldirildi"
        else:
            return "IMBALANCE: Bearish FVG to'ldirilmagan — Narx qaytishi kutilmoqda"

    return "IMBALANCE: Aniqlanmadi"


def detect_wyckoff_phase(df: pd.DataFrame) -> str:
    """
    Professionalroq Wyckoff reading:
    - range aniqlaydi
    - spring / upthrust ni ushlaydi
    - breakout continuation bo'lsa markup / markdown qaytaradi
    - aks holda ranging / accumulation / distributionni ajratadi
    """
    if df is None or len(df) < 30:
        return "WYCKOFF: Aniqlik uchun data yetarli emas"

    recent = df.tail(60).copy().reset_index(drop=True)
    if len(recent) < 30:
        return "WYCKOFF: Aniqlik uchun data yetarli emas"

    recent["range"] = recent["high"] - recent["low"]
    avg_range = recent["range"].tail(20).mean()

    if pd.isna(avg_range) or avg_range <= 0:
        avg_range = 5.0

    current = recent.iloc[-1]
    prev = recent.iloc[-2]

    current_open = float(current["open"])
    current_high = float(current["high"])
    current_low = float(current["low"])
    current_close = float(current["close"])

    prev_close = float(prev["close"])

    current_body = abs(current_close - current_open)
    current_range = current_high - current_low

    core = recent.iloc[-21:-1].copy()
    if core.empty:
        return "WYCKOFF: Aniqlanmadi"

    range_high = float(core["high"].max())
    range_low = float(core["low"].min())
    range_width = range_high - range_low

    if range_width <= 0:
        return "WYCKOFF: Aniqlanmadi"

    breakout_buffer = max(avg_range * 0.15, 0.80)
    sweep_buffer = max(avg_range * 0.20, 1.00)
    proximity = max(avg_range * 0.35, 1.50)

    recent_mean_range = recent["range"].tail(8).mean()
    compression = recent_mean_range <= avg_range * 0.85

    near_range_low = current_close <= range_low + proximity
    near_range_high = current_close >= range_high - proximity

    bullish_close = current_close > current_open
    bearish_close = current_close < current_open

    broke_up = (
        current_close > range_high + breakout_buffer
        and current_range >= avg_range * 1.05
        and current_close > prev_close
    )

    broke_down = (
        current_close < range_low - breakout_buffer
        and current_range >= avg_range * 1.05
        and current_close < prev_close
    )

    spring = (
        current_low < range_low - sweep_buffer
        and current_close > range_low
        and bullish_close
    )

    upthrust = (
        current_high > range_high + sweep_buffer
        and current_close < range_high
        and bearish_close
    )

    # Markup / Markdown continuation
    if broke_up:
        return (
            f"WYCKOFF: MARKUP — Range yuqoriga buzildi "
            f"({range_low:.2f}-{range_high:.2f}), bullish continuation"
        )

    if broke_down:
        return (
            f"WYCKOFF: MARKDOWN — Range pastga buzildi "
            f"({range_low:.2f}-{range_high:.2f}), bearish continuation"
        )

    # Spring / Upthrust
    if spring:
        return (
            f"WYCKOFF: ACCUMULATION — Spring kuzatildi, "
            f"range low sweep qilinib qaytildi ({range_low:.2f})"
        )

    if upthrust:
        return (
            f"WYCKOFF: DISTRIBUTION — Upthrust kuzatildi, "
            f"range high sweep qilinib rad etildi ({range_high:.2f})"
        )

    # Compression-based context
    if compression and near_range_low:
        return (
            f"WYCKOFF: ACCUMULATION — Range pastida siqilish, "
            f"demand yig'ilishi ehtimoli ({range_low:.2f}-{range_high:.2f})"
        )

    if compression and near_range_high:
        return (
            f"WYCKOFF: DISTRIBUTION — Range tepasida siqilish, "
            f"taklif kuchayishi ehtimoli ({range_low:.2f}-{range_high:.2f})"
        )

    # General ranging
    if range_low <= current_close <= range_high:
        return (
            f"WYCKOFF: RANGING — Konsolidatsiya "
            f"({range_low:.2f}-{range_high:.2f}), breakout kutilmoqda"
        )

    return "WYCKOFF: Aniqlanmadi"


def calculate_confluence_score(
    h1_trend:      str,
    m15_trend:     str,
    rsi_text:      str,
    macd_text:     str,
    candle:        str,
    fvg:           dict,
    wyckoff:       str,
    market_struct: str,
    session:       str,
    volume:        str,
    divergence:    str,
) -> dict:
    """
    Confluence Score — Barcha signallarning umumiy kuchi.

    Pro treyderlar bir vaqtda ko'plab tasdiqlarni tekshiradi.
    Har bir tasdiq ball qo'shadi.
    Jami ball = signal ishonchliligi.

    Maksimal ball: 20
    10+ = Kuchli signal
    7-9 = O'rta signal
    5-6 = Zaif signal
    <5  = Trade yo'q
    """
    score    = 0
    details  = []

    # 1. Multi-timeframe alignment (+3 ball)
    if "Bullish" in h1_trend and "Bullish" in m15_trend:
        score += 3
        details.append("✓ H1+M15 Bullish alignment (+3)")
    elif "Bearish" in h1_trend and "Bearish" in m15_trend:
        score += 3
        details.append("✓ H1+M15 Bearish alignment (+3)")
    elif h1_trend != m15_trend:
        score += 0
        details.append("✗ Timeframe ziddiyat (0)")

    # 2. RSI (+2 ball)
    if "Oversold" in rsi_text:
        score += 2
        details.append("✓ RSI Oversold — BUY signal (+2)")
    elif "Overbought" in rsi_text:
        score += 2
        details.append("✓ RSI Overbought — SELL signal (+2)")
    elif "Bullish" in rsi_text or "Bearish" in rsi_text:
        score += 1
        details.append("✓ RSI momentum (+1)")

    # 3. MACD (+2 ball)
    if "Bullish" in macd_text:
        score += 2
        details.append("✓ MACD Bullish (+2)")
    elif "Bearish" in macd_text:
        score += 2
        details.append("✓ MACD Bearish (+2)")

    # 4. Candle confirmation (+3 ball)
    if "Strong" in candle or "Sweep" in candle or "Engulfing" in candle:
        score += 3
        details.append("✓ Kuchli sham tasdiq (+3)")
    elif "Bullish" in candle or "Bearish" in candle:
        score += 1
        details.append("✓ Sham tasdiq (+1)")

    # 5. FVG (+2 ball)
    if fvg.get("in_zone"):
        score += 2
        details.append(f"✓ FVG zonasida (+2): {fvg.get('type')}")
    elif fvg.get("type") != "No FVG":
        score += 1
        details.append(f"✓ FVG mavjud (+1)")

    # 6. Wyckoff (+2 ball)
    if "MARKUP" in wyckoff and "zaif" not in wyckoff:
        score += 2
        details.append("✓ Wyckoff MARKUP (+2)")
    elif "MARKDOWN" in wyckoff and "zaif" not in wyckoff:
        score += 2
        details.append("✓ Wyckoff MARKDOWN (+2)")
    elif "ACCUMULATION" in wyckoff:
        score += 1
        details.append("✓ Wyckoff ACCUMULATION (+1)")

    # 7. Market structure (+2 ball)
    if "Bullish" in market_struct:
        score += 2
        details.append("✓ Bullish market structure (+2)")
    elif "Bearish" in market_struct:
        score += 2
        details.append("✓ Bearish market structure (+2)")

    # 8. Session (+1 ball)
    if "OVERLAP" in session:
        score += 1
        details.append("✓ London+NY Overlap (+1)")
    elif "LONDON" in session or "NEW YORK" in session:
        score += 1
        details.append("✓ Kuchli sessiya (+1)")

    # 9. Volume (+1 ball)
    if "Yuqori" in volume:
        score += 1
        details.append("✓ Yuqori volume (+1)")

    # 10. Divergence (+2 ball)
    if "BULLISH DIVERGENCE: Kuchli" in divergence:
        score += 2
        details.append("✓ Kuchli Bullish Divergence (+2)")
    elif "BEARISH DIVERGENCE: Kuchli" in divergence:
        score += 2
        details.append("✓ Kuchli Bearish Divergence (+2)")

    # Daraja aniqlash
    if score >= 10:
        grade = "STRONG"
        emoji = "🔥"
    elif score >= 7:
        grade = "MEDIUM"
        emoji = "⚡"
    elif score >= 5:
        grade = "WEAK"
        emoji = "⚠️"
    else:
        grade = "NO TRADE"
        emoji = "❌"

    return {
        "score":   score,
        "grade":   grade,
        "emoji":   emoji,
        "details": details,
        "text":    f"CONFLUENCE: {score}/20 — {grade} {emoji}",
    }