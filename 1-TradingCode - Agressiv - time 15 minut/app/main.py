from datetime import datetime
import os
import glob
from outcome_tracker import run_outcome_tracker
import matplotlib.pyplot as plt
from mt5_client import connect_mt5, disconnect_mt5
from analyzer import run_analysis
from config import SIGNAL_MODE, ENABLE_AUTO_TRADE, LOT_SIZE, SYMBOL
from trader import place_split_dca_orders, monitor_virtual_sl
from tg_bot import start_telegram_listener
from reporter import (
    show_analysis_report,
    show_price_table,
    save_analysis_to_file,
    save_bars_to_csv,
    show_final_decision,
    show_run_context,
    save_signal_journal,
    show_signal_stats,
    show_recent_signals,
    show_actionable_signals,
    show_hot_signals,
    show_ready_signal_banner,
    show_signal_mode,
    show_execution_signal_banner,
    send_telegram_alert,
    send_telegram_photo,
    play_signal_sound,
)

def clean_garbage_files():
    """Eski bars va analysis fayllarini avtomatik tozalaydi, faqat eng oxirgi 30 tasini saqlaydi"""
    folders_to_clean = [
        {"path": "data", "pattern": "bars_*.csv"},
        {"path": "logs", "pattern": "analysis_*.txt"}
    ]
    
    keep_count = 30 
    
    for item in folders_to_clean:
        try:
            if not os.path.exists(item["path"]): continue
            search_path = os.path.join(item["path"], item["pattern"])
            files = glob.glob(search_path)
            files.sort(key=os.path.getmtime)
            
            if len(files) > keep_count:
                files_to_delete = files[:-keep_count] 
                for f in files_to_delete:
                    os.remove(f)
                print(f"🧹 Tozalandi: {len(files_to_delete)} ta eski '{item['pattern']}' fayli.")
        except Exception as e:
            print(f"Tozalashda xatolik: {e}")


def append_reason(result: dict, new_reason: str):
    old_reason = str(result.get("reason", "")).strip()

    if not old_reason:
        result["reason"] = new_reason
        return

    if new_reason and new_reason not in old_reason:
        result["reason"] = f"{old_reason} | {new_reason}"


def run_once():
    if not connect_mt5():
        return

    try:
        # Virtual Stop Loss nazorati (Sham yopilishini kutish algoritmi)
        monitor_virtual_sl(SYMBOL) 

        result = run_analysis()

        if result is None:
            print("Tahlil natijasi olinmadi.")
            return

        # 2. Tashqi final filterlar
        if result["is_news_time"]:
            result["final_signal"] = "WAIT"
            append_reason(result, f"STOP: {result['news_reason']}")

        # 5. Konsolga hisobotlar
        show_run_context(
            symbol=result["symbol"],
            h1_timeframe_name=result["h1_timeframe_name"],
            m15_timeframe_name=result["m15_timeframe_name"],
        )

        # Faza 4: Market structure
        print(f"\n{'='*50}")
        print(f"MARKET STRUCTURE : {result.get('market_structure', 'N/A')}")
        print(f"ORDER BLOCK      : {result.get('order_block', 'N/A')}")
        print(f"LIQUIDITY ZONES  : {result.get('liquidity_zones', 'N/A')}")
        print(f"FVG              : {result.get('fvg_text', 'N/A')}")
        print(f"BREAKER BLOCK    : {result.get('breaker_block', 'N/A')}")
        print(f"IMBALANCE        : {result.get('imbalance_fill', 'N/A')}")
        print(f"WYCKOFF          : {result.get('wyckoff_phase', 'N/A')}")
        print(f"CONFLUENCE       : {result.get('confluence_text', 'N/A')}")
        print(f"ML FILTER     : {result.get('ml_reason', 'N/A')}")
        for detail in result.get('confluence', {}).get('details', []):
            print(f"  {detail}")
        print(f"{'='*50}\n")

        show_signal_mode(SIGNAL_MODE)

        if result.get("session_ok", True):
            show_price_table(result["m15_df"])
        else:
            print("Narx jadvali ko'rsatilmadi: session filter blokladi.")

        # Faza 2
        print(f"\nSESSIYA    : {result['session_status']}")
        print(f"VOLUME     : {result['volume_status']}")
        print(f"STOCH RSI  : {result['stoch_rsi_text']}")
        print(f"DIVERGENCE : {result['divergence_text']}")
        print("-" * 50)

        show_analysis_report(
            h1_timeframe_name=result["h1_timeframe_name"],
            m15_timeframe_name=result["m15_timeframe_name"],
            h1_trend=result["h1_trend"],
            m15_trend=result["m15_trend"],
            alignment_text=result["alignment_text"],
            rsi_value=result["last_rsi"],
            rsi_text=result["rsi_text"],
            macd_text=result["macd_text"],
            candle_confirmation=result["candle_confirmation"],
            support=result["support"],
            resistance=result["resistance"],
            atr_value=result["atr_value"],
            price_location=result["price_location"],
            entry_zone_text=result["entry_zone_text"],
            summary=result["summary"],
            trade_comment=result["trade_comment"],
            setup_status=result["setup_status"],
            signal_strength=result["signal_strength"],
            trade_plan=result["trade_plan"],
            final_signal=result["final_signal"],
            alert_message=result["alert_message"],
            reason=result["reason"],
            suggested_entry=result["suggested_entry"],
            suggested_sl=result["suggested_sl"],
            suggested_tp=result["suggested_tp"],
            risk_reward_ratio=result["risk_reward_ratio"],
        )

        show_final_decision(
            h1_timeframe_name=result["h1_timeframe_name"],
            m15_timeframe_name=result["m15_timeframe_name"],
            final_signal=result["final_signal"],
            setup_status=result["setup_status"],
            signal_strength=result["signal_strength"],
            trade_plan=result["trade_plan"],
            alert_message=result["alert_message"],
            reason=result["reason"],
            signal_mode=SIGNAL_MODE,
        )

        # 6. Ovoz va bannerlar
        play_signal_sound(
            setup_status=result["setup_status"],
            final_signal=result["final_signal"],
        )

        show_ready_signal_banner(result)
        show_execution_signal_banner(result)

        # Faza 3: Risk Management
        if result["final_signal"] in ["BUY", "SELL"]:
            print("\n" + "=" * 50)
            print("  RISK MANAGEMENT PLAN")
            print("=" * 50)
            print(f"Entry      : {result['suggested_entry']}")
            print(f"Stop Loss  : {result['suggested_sl']}")
            print(f"D1 Trend   : {result.get('d1_trend', 'N/A')}")
            print(f"DXY Status : {result.get('dxy_status', 'N/A')}")
            print(f"ML Filter  : {result.get('ml_reason', 'N/A')}")
            print(f"TP1 (1:1.5): {result['tp1']}  <- 33% lot yoping")
            print(f"TP2 (1:2.5): {result['tp2']}  <- 33% lot yoping")
            print(f"TP3 (1:4.0): {result['tp3']}  <- 34% lot yoping")
            if result['trailing_sl']:
                print(f"Trailing SL: {result['trailing_sl']}")
            if result['breakeven_active']:
                print(f"Breakeven  : {result['breakeven_sl']} <- AKTIV!")
            print("=" * 50)

        # Avto trade (Agressiv DCA va Virtual SL rejimi)
        if result["final_signal"] in ["BUY", "SELL"]:
            if ENABLE_AUTO_TRADE:
                success, order_message = place_split_dca_orders(
                    symbol=result["symbol"],
                    signal=result["final_signal"],
                    total_lot=LOT_SIZE,
                    atr=result["atr_value"],
                    current_price=result["suggested_entry"],
                    virtual_sl=result["suggested_sl"],
                    tp=result["suggested_tp"]
                )
                print(order_message)
                append_reason(result, order_message)
            else:
                print("AUTO TRADE OFF: order ochilmadi (Agressiv DCA Mode)")
                append_reason(result, "AUTO TRADE OFF - Virtual SL Active")

            # Telegram uchun jozibali ma'lumotlarni tayyorlash
            atr_val = result.get('atr_value', 0)
            entry1 = result.get('suggested_entry', 0)
            if result["final_signal"] == "BUY":
                entry2 = round(entry1 - (atr_val * 0.5), 2)
                direction_emoji, limit_emoji = "🟢", "🔵"
            else:
                entry2 = round(entry1 + (atr_val * 0.5), 2)
                direction_emoji, limit_emoji = "🔴", "🟠"
                
            screenshot_path = os.path.join(os.getcwd(), "chart_snapshot.png")
            try:
                chart_df = result["m15_df"]

                fig, (ax1, ax2) = plt.subplots(
                    2, 1,
                    figsize=(14, 8),
                    gridspec_kw={"height_ratios": [3, 1]},
                    facecolor="#0d1117"
                )

                COLOR_BG   = "#0d1117"
                COLOR_UP   = "#26a69a"
                COLOR_DOWN = "#ef5350"
                COLOR_EMA20= "#f6c90e"
                COLOR_EMA50= "#2196f3"
                COLOR_ENTRY= "#ffffff"
                COLOR_SL   = "#ef5350"
                COLOR_TP1  = "#26a69a"
                COLOR_TP2  = "#00e5ff"
                COLOR_TP3  = "#b2ff59"
                COLOR_TEXT = "#e0e0e0"

                df_chart = chart_df.tail(60).copy()
                df_chart = df_chart.reset_index(drop=True)

                ax1.set_facecolor(COLOR_BG)
                ax2.set_facecolor(COLOR_BG)

                for i, row in df_chart.iterrows():
                    color = COLOR_UP if row["close"] >= row["open"] else COLOR_DOWN
                    ax1.bar(i, abs(row["close"] - row["open"]),
                            bottom=min(row["open"], row["close"]),
                            color=color, width=0.6, linewidth=0)
                    ax1.plot([i, i], [row["low"], row["high"]],
                             color=color, linewidth=0.8)

                ax1.plot(df_chart.index, df_chart["EMA_20"],
                         color=COLOR_EMA20, linewidth=1.2, label="EMA 20")
                ax1.plot(df_chart.index, df_chart["EMA_50"],
                         color=COLOR_EMA50, linewidth=1.2, label="EMA 50")

                entry = result.get("suggested_entry")
                sl    = result.get("suggested_sl")
                tp1   = result.get("tp1")
                tp2   = result.get("tp2")
                tp3   = result.get("tp3")

                if entry:
                    ax1.axhline(entry, color=COLOR_ENTRY, linewidth=1.0,
                                linestyle="--", label=f"Entry {entry}")
                if sl:
                    ax1.axhline(sl, color=COLOR_SL, linewidth=1.0,
                                linestyle="--", label=f"SL {sl}")
                if tp1:
                    ax1.axhline(tp1, color=COLOR_TP1, linewidth=1.0,
                                linestyle=":", label=f"TP1 {tp1}")
                if tp2:
                    ax1.axhline(tp2, color=COLOR_TP2, linewidth=1.0,
                                linestyle=":", label=f"TP2 {tp2}")
                if tp3:
                    ax1.axhline(tp3, color=COLOR_TP3, linewidth=1.0,
                                linestyle=":", label=f"TP3 {tp3}")

                step     = max(1, len(df_chart) // 8)
                tick_pos = list(range(0, len(df_chart), step))
                tick_lbls= [
                    df_chart["time"].iloc[i].strftime("%m/%d %H:%M")
                    for i in tick_pos
                ]

                ax1.set_xticks(tick_pos)
                ax1.set_xticklabels(tick_lbls, rotation=45,
                                    fontsize=7, color=COLOR_TEXT)
                ax1.tick_params(colors=COLOR_TEXT)
                ax1.yaxis.tick_right()
                ax1.yaxis.set_tick_params(labelcolor=COLOR_TEXT)
                ax1.legend(loc="upper left", fontsize=7,
                           facecolor=COLOR_BG, labelcolor=COLOR_TEXT)
                ax1.set_title(
                    f"XAUUSD M15  |  {result['final_signal']}  |  "
                    f"Setup: {result['setup_status']}  |  "
                    f"Strength: {result['signal_strength']}",
                    color=COLOR_TEXT, fontsize=10, pad=8
                )
                ax1.grid(color="#1e2a38", linewidth=0.4)
                ax1.spines[:].set_color("#1e2a38")

                rsi_vals = df_chart["RSI"].values
                ax2.plot(df_chart.index, rsi_vals,
                         color="#ce93d8", linewidth=1.0)
                ax2.axhline(70, color=COLOR_DOWN, linewidth=0.6, linestyle="--")
                ax2.axhline(30, color=COLOR_UP,   linewidth=0.6, linestyle="--")
                ax2.axhline(50, color="#555",      linewidth=0.4, linestyle=":")
                ax2.fill_between(df_chart.index, rsi_vals, 70,
                                 where=[v > 70 for v in rsi_vals],
                                 color=COLOR_DOWN, alpha=0.2)
                ax2.fill_between(df_chart.index, rsi_vals, 30,
                                 where=[v < 30 for v in rsi_vals],
                                 color=COLOR_UP, alpha=0.2)
                ax2.set_ylim(0, 100)
                ax2.set_yticks([30, 50, 70])
                ax2.tick_params(colors=COLOR_TEXT, labelsize=7)
                ax2.set_ylabel("RSI", color=COLOR_TEXT, fontsize=8)
                ax2.set_xticks(tick_pos)
                ax2.set_xticklabels(tick_lbls, rotation=45,
                                    fontsize=7, color=COLOR_TEXT)
                ax2.grid(color="#1e2a38", linewidth=0.4)
                ax2.spines[:].set_color=("#1e2a38")

                info = (
                    f"RSI: {result['last_rsi']:.1f}  |  "
                    f"ATR: {result['atr_value']:.2f}  |  "
                    f"S: {result['support']:.2f}  |  "
                    f"R: {result['resistance']:.2f}  |  "
                    f"{result['session_status'].split(':')[0]}  |  "
                    f"{result['volume_status'].split(':')[1].strip()}"
                )
                fig.text(0.01, 0.01, info,
                         color=COLOR_TEXT, fontsize=7,
                         verticalalignment="bottom")

                plt.tight_layout(rect=[0, 0.03, 1, 1])
                plt.savefig(screenshot_path, dpi=130,
                            bbox_inches="tight", facecolor=COLOR_BG)
                plt.close()

                emoji = "🚀 BUY" if result["final_signal"] == "BUY" else "🔥 SELL"
                caption = (
                    f"<b>{emoji} SIGNAL DETECTED! (DCA Mode)</b>\n"
                    f"➖➖➖➖➖➖➖➖➖➖➖\n\n"
                    
                    f"📊 <b>Symbol:</b> {result['symbol']}\n"
                    f"⏰ <b>Sessiya:</b> {result['session_status'].split(':')[0]}\n"
                    f"🛡 <b>Virtual SL:</b> <code>{result['suggested_sl']}</code> 🥷 (Hidden)\n"
                    f"<i>⚠️ (Faqat sham yopilganda yopiladi!)</i>\n\n"
                    
                    f"➖➖➖ <b>KIRISH ZONALARI</b> ➖➖➖\n"
                    f"{direction_emoji} <b>Entry 1 (Market):</b> <code>{entry1}</code>\n"
                    f"{limit_emoji} <b>Entry 2 (Limit):</b> <code>{entry2}</code> 🕸\n"
                    f"<i>(Pulback masofasi: {atr_val*0.5:.2f})</i>\n\n"
                    
                    f"➖➖➖ <b>PROFIT ZONALARI</b> ➖➖➖\n"
                    f"🎯 <b>TP 1 (Safe):</b> {result['tp1']}\n"
                    f"🎯 <b>TP 2 (Main):</b> {result['tp2']}\n"
                    f"🚀 <b>TP 3 (Max):</b> {result['tp3']}\n\n"
                    
                    f"➖➖➖ <b>TAHLIL</b> ➖➖➖\n"
                    f"⚖️ <b>Risk/Reward:</b> {result['risk_reward_ratio']}\n"
                    f"🔥 <b>Confluence:</b> {result['confluence_score']}/20\n"
                    f"📐 <b>Structure:</b> {result.get('market_structure', 'N/A').split(':')[1].strip() if ':' in result.get('market_structure', '') else 'N/A'}\n"
                    f"📦 <b>FVG:</b> {result.get('fvg_text', 'N/A').split(':')[1].strip() if ':' in result.get('fvg_text', '') else 'N/A'}\n"
                    f"🏦 <b>Wyckoff:</b> {result.get('wyckoff_phase', 'N/A').split(':')[1].strip() if ':' in result.get('wyckoff_phase', '') else 'N/A'}\n\n"
                    
                    f"📝 <b>Izoh:</b> {result['reason']}"
                )
                send_telegram_photo(screenshot_path, caption)

            except Exception as e:
                print(f"Chart yaratishda xatolik: {e}")
                send_telegram_alert(result)

        # 8. Log va statistika
        save_analysis_to_file(result)
        save_bars_to_csv(result)
        save_signal_journal(result)
        show_signal_stats()
        show_recent_signals()
        show_actionable_signals()
        show_hot_signals()

    finally:
        disconnect_mt5()


def run_with_protection():
    """
    Xavfsiz ishga tushirish — xato bo'lsa ham davom etadi.
    """
    try:
        run_once()
    except Exception as e:
        print(f"[XATO] {datetime.now().strftime('%H:%M:%S')} — {e}")
        print("Keyingi siklda qayta uriniladi...")
    
    clean_garbage_files()


def start():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    start_telegram_listener()

    print("=" * 50)
    print("  GOLD TRADING BOT: SCHEDULER MODE")
    print("  Har 15 daqiqada aniq vaqtda ishlaydi")
    print("  To'xtatish: Ctrl+C")
    print("=" * 50)

    scheduler = BlockingScheduler(timezone="Asia/Tashkent")

    # Har 15 daqiqada — 0, 15, 30, 45 da
    scheduler.add_job(
        run_with_protection,
        trigger=CronTrigger(minute="0,15,30,45"),
        id="gold_bot",
        name="Gold Trading Bot",
        max_instances=1,        # Bir vaqtda faqat 1 ta instance
        misfire_grace_time=60,  # 60 soniya kechiksa ham ishga tushiradi
    )

    # Birinchi marta darhol ishga tushirish
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Bot ishga tushdi!")
    print("Birinchi tahlil boshlanmoqda...\n")
    run_with_protection()

    # Har soatda outcome tracker ishga tushadi
    scheduler.add_job(
        run_outcome_tracker,
        trigger=CronTrigger(minute="0"),  # Har soat boshida
        id="outcome_tracker",
        name="Outcome Tracker",
        max_instances=1,
        misfire_grace_time=60,
    )

    # Scheduler ni boshlash
    try:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scheduler ishga tushdi.")
        print("Keyingi tahlil: 0, 15, 30 yoki 45 daqiqada\n")
        scheduler.start()

    except KeyboardInterrupt:
        print("\nBot to'xtatildi!")
        scheduler.shutdown()


if __name__ == "__main__":
    start()