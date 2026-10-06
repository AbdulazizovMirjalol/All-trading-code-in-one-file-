# 🚀 GOLD TRADING BOT (XAUUSD)

Professional automated trading analysis system for XAUUSD (Gold), built with multi-timeframe logic, strict filters, journaling, and ML-ready architecture.

---

# 📊 SYSTEM OVERVIEW

This system:

* Analyzes XAUUSD every 15 minutes
* Uses M15 + H1 + D1 timeframe logic
* Applies strict filters (session, news, confluence)
* Generates signals: **BUY / SELL / WAIT**
* Logs all data for analysis
* Tracks trade outcomes (WIN / LOSS)
* Prepares data for Machine Learning

---

# ⚙️ FEATURES

## 🔹 Core Engine

* Multi-timeframe analysis (M15, H1, D1)
* EMA, RSI, MACD, ATR indicators
* Smart Money concepts (FVG, Wyckoff, Structure)

## 🔹 Filters

* Session filter (Asia / London / NY)
* High-impact news filter
* Confluence scoring system

## 🔹 Signal System

* Setup status (READY / NO TRADE / WATCH)
* Signal strength (WEAK / MEDIUM / STRONG)
* Final signal decision

## 🔹 Risk Management

* Stop Loss / Take Profit
* Risk/Reward ratio
* Multi TP levels
* Breakeven & trailing logic

## 🔹 Logging

* signal_journal.csv
* analysis logs
* market data logs

## 🔹 ML System (READY but OFF)

* XGBoost model
* Feature engineering pipeline
* Probability-based filtering
* Readiness checker

---

# ▶️ HOW TO RUN

## Run main bot

```bash
py app/main.py
```

## Check ML readiness

```bash
py app/ml_model.py
```

## Run outcome tracker

```bash
py app/outcome_tracker.py
```

---

# 📁 PROJECT STRUCTURE

```
app/
 ├── main.py
 ├── analyzer.py
 ├── ml_model.py
 ├── outcome_tracker.py
 ├── reporter.py
 ├── indicators.py
 ├── signal_engine.py

logs/
 ├── signal_journal.csv
 ├── analysis_*.txt
 ├── bars_*.csv
```

---

# 📦 INSTALLATION

```bash
pip install -r requirements.txt
```

---

# 🧠 MACHINE LEARNING (IMPORTANT)

ML is **disabled by default**.

## ❌ DO NOT ENABLE UNTIL:

* At least **50 signals** with WIN/LOSS
* At least **10 WIN**
* At least **10 LOSS**

## ✅ Check readiness:

```bash
py app/ml_model.py
```

If you see:

```
STATUS: ML ni yoqish mumkin ✅
```

Then enable in config:

```python
ENABLE_ML_FILTER = True
```

---

# 📅 DAILY CHECKLIST

Every day:

### ✅ System

* Bot is running
* No terminal errors

### ✅ Logs

* signal_journal.csv updating
* No corrupted data

### ✅ Signals

* Many WAIT → normal
* No trades → normal early phase

### ✅ ML readiness

```
py app/ml_model.py
```

---

# ⚠️ IMPORTANT RULES

## ❌ DO NOT:

* Enable ML too early
* Change strategy randomly
* Force trades

## ✅ DO:

* Let system collect data
* Monitor logs
* Stay consistent

---

# 🧪 CURRENT PHASE

You are in:

## 👉 DATA COLLECTION MODE

Goal:

* Build dataset
* Collect real outcomes
* Prepare ML training

---

# 🛠 TROUBLESHOOTING

## MT5 not connecting

* Make sure MetaTrader5 is running
* Check account login

## No signals

* Normal (filters working)
* Especially during Asia session

## ML not working

```
py app/ml_model.py
```

## CSV errors

* Close Excel before running bot

---

# 🔥 SYSTEM STATUS

* Core system: ✅ READY
* Logging: ✅ READY
* Filters: ✅ ACTIVE
* ML: ⏳ WAITING FOR DATA

---

# 🎯 NEXT STEP

After enough data:

1. Train ML model
2. Enable ML filter
3. Improve performance

---

# 💎 FINAL NOTE

This is not just a bot.
This is a **data-driven trading system**.

