"""
ml_model.py — XGBoost asosida signal filtri.

Ishlash tartibi:
  1. signal_journal.csv dan ma'lumot o'qiydi
  2. outcome (WIN/LOSS) ustuni asosida model o'qitadi
  3. Yangi signal kelganda ehtimollik beradi
  4. 65%+ bo'lsa signal o'tadi, aks holda WAIT

MUHIM:
- Model yo'q bo'lsa bot signalni bloklamaydi
- Feature lar hozirgi signal_journal schema bilan moslangan
- Train/test split vaqt tartibida qilinadi (chronological split)
- WIN/LOSS balans juda yomon bo'lsa ML gate majburan yoqilmaydi
"""

from pathlib import Path
import pickle
import pandas as pd

JOURNAL_PATH = Path("logs/signal_journal.csv")
MODEL_PATH = Path("logs/ml_model.pkl")

MIN_SAMPLES = 50
MIN_PROB = 0.65
MIN_CLASS_SAMPLES = 10
MODEL_VERSION = "xgb_feature_audit_v3"


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────
def _str_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return df[col].fillna("").astype(str)


def _num_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([0.0] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def _contains(series: pd.Series, pattern: str) -> pd.Series:
    return series.str.contains(pattern, case=False, na=False).astype(int)


def _trend_to_num(series: pd.Series) -> pd.Series:
    return series.apply(
        lambda x: 1 if "bull" in str(x).lower()
        else -1 if "bear" in str(x).lower()
        else 0
    ).astype(int)


# ─────────────────────────────────────────
# Feature Engineering
# ─────────────────────────────────────────
def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    signal_journal.csv dagi hozirgi schema bo'yicha ML feature lar tayyorlaydi.
    """
    features = pd.DataFrame(index=df.index)

    # Numeric core
    features["rsi"] = _num_series(df, "rsi")
    features["atr"] = _num_series(df, "atr")
    features["confluence_score"] = _num_series(df, "confluence_score")
    features["rr_ratio"] = _num_series(df, "risk_reward_ratio")
    features["entry_price"] = _num_series(df, "entry_price")
    features["stop_loss"] = _num_series(df, "stop_loss")
    features["take_profit"] = _num_series(df, "take_profit")
    features["tp1"] = _num_series(df, "tp1")
    features["tp2"] = _num_series(df, "tp2")
    features["tp3"] = _num_series(df, "tp3")
    features["ml_probability_prev"] = _num_series(df, "ml_probability")

    # Trend stack
    h1_trend = _str_series(df, "h1_trend")
    m15_trend = _str_series(df, "m15_trend")
    d1_trend = _str_series(df, "d1_trend")

    features["h1_trend"] = _trend_to_num(h1_trend)
    features["m15_trend"] = _trend_to_num(m15_trend)
    features["d1_trend"] = _trend_to_num(d1_trend)

    features["h1_m15_aligned"] = (features["h1_trend"] == features["m15_trend"]).astype(int)
    features["d1_h1_aligned"] = (features["d1_trend"] == features["h1_trend"]).astype(int)
    features["three_tf_aligned"] = (
        (features["d1_trend"] == features["h1_trend"]) &
        (features["h1_trend"] == features["m15_trend"]) &
        (features["h1_trend"] != 0)
    ).astype(int)

    # Signal direction
    final_signal = _str_series(df, "final_signal").str.upper().str.strip()
    features["is_buy"] = (final_signal == "BUY").astype(int)
    features["is_sell"] = (final_signal == "SELL").astype(int)

    # Setup / strength
    setup_status = _str_series(df, "setup_status")
    signal_strength = _str_series(df, "signal_strength")

    features["setup_ready_buy"] = _contains(setup_status, r"READY BUY")
    features["setup_ready_sell"] = _contains(setup_status, r"READY SELL")
    features["setup_buy_watch"] = _contains(setup_status, r"BUY WATCH")
    features["setup_sell_watch"] = _contains(setup_status, r"SELL WATCH")
    features["setup_no_trade"] = _contains(setup_status, r"NO TRADE")

    features["strength_strong"] = _contains(signal_strength, r"STRONG")
    features["strength_medium"] = _contains(signal_strength, r"MEDIUM")
    features["strength_weak"] = _contains(signal_strength, r"WEAK")

    # Actionability
    actionable = _str_series(df, "actionable")
    hot_signal = _str_series(df, "hot_signal")
    ml_approved = _str_series(df, "ml_approved")

    features["actionable_yes"] = actionable.apply(
        lambda x: 1 if str(x).strip().lower() in ["yes", "true", "1"] else 0
    ).astype(int)
    features["hot_signal_yes"] = hot_signal.apply(
        lambda x: 1 if str(x).strip().lower() in ["yes", "true", "1"] else 0
    ).astype(int)
    features["ml_approved_prev"] = ml_approved.apply(
        lambda x: 1 if str(x).strip().lower() in ["yes", "true", "1"] else 0
    ).astype(int)

    # RSI / MACD / candle / stoch
    rsi_status = _str_series(df, "rsi_status")
    macd_status = _str_series(df, "macd_status")
    candle_confirmation = _str_series(df, "candle_confirmation")
    stoch_rsi_signal = _str_series(df, "stoch_rsi_signal")

    features["rsi_bullish"] = _contains(rsi_status, r"bull")
    features["rsi_bearish"] = _contains(rsi_status, r"bear")
    features["rsi_oversold"] = _contains(rsi_status, r"oversold")
    features["rsi_overbought"] = _contains(rsi_status, r"overbought")

    features["macd_bullish"] = _contains(macd_status, r"bull")
    features["macd_bearish"] = _contains(macd_status, r"bear")

    features["candle_bullish"] = _contains(candle_confirmation, r"bull|engulf|strong")
    features["candle_bearish"] = _contains(candle_confirmation, r"bear|engulf|strong")

    features["stoch_overbought"] = _contains(stoch_rsi_signal, r"overbought")
    features["stoch_oversold"] = _contains(stoch_rsi_signal, r"oversold")
    features["stoch_buy"] = _contains(stoch_rsi_signal, r"\bbuy\b")
    features["stoch_sell"] = _contains(stoch_rsi_signal, r"\bsell\b")

    # Session / filters
    session_status = _str_series(df, "session_status")
    dxy_status = _str_series(df, "dxy_status")
    news_reason = _str_series(df, "news_reason")
    news_blocked_raw = _str_series(df, "news_blocked")
    volume_status = _str_series(df, "volume_status")

    features["london_session"] = _contains(session_status, r"LONDON")
    features["ny_session"] = _contains(session_status, r"NEW YORK")
    features["overlap_session"] = _contains(session_status, r"OVERLAP")
    features["asia_session"] = _contains(session_status, r"ASIA")
    features["strong_session"] = _contains(session_status, r"kuchli|strong")

    features["dxy_strengthening"] = _contains(dxy_status, r"STRENGTHENING")
    features["dxy_weakening"] = _contains(dxy_status, r"WEAKENING")
    features["dxy_flat"] = _contains(dxy_status, r"FLAT")
    features["dxy_unknown"] = _contains(dxy_status, r"UNKNOWN")

    features["news_blocked"] = news_blocked_raw.apply(
        lambda x: 1 if str(x).strip().lower() in ["true", "1", "yes"] else 0
    ).astype(int)
    features["news_high_impact"] = _contains(news_reason, r"high impact|fomc|cpi|powell|rate")

    features["high_volume"] = _contains(volume_status, r"yuqori|high")
    features["low_volume"] = _contains(volume_status, r"past|low|weak")

    # Structure / confluence stack
    fvg_text = _str_series(df, "fvg_text")
    order_block = _str_series(df, "order_block")
    breaker_block = _str_series(df, "breaker_block")
    liquidity_zones = _str_series(df, "liquidity_zones")
    imbalance_fill = _str_series(df, "imbalance_fill")
    wyckoff_phase = _str_series(df, "wyckoff_phase")
    market_structure = _str_series(df, "market_structure")
    divergence_text = _str_series(df, "divergence_text")

    features["bullish_fvg"] = _contains(fvg_text, r"bullish")
    features["bearish_fvg"] = _contains(fvg_text, r"bearish")
    features["fvg_open"] = _contains(fvg_text, r"aktiv|open")
    features["fvg_partial"] = _contains(fvg_text, r"qisman|partial")

    features["bullish_ob"] = _contains(order_block, r"bullish")
    features["bearish_ob"] = _contains(order_block, r"bearish")

    features["bullish_breaker"] = _contains(breaker_block, r"bullish")
    features["bearish_breaker"] = _contains(breaker_block, r"bearish")

    features["buy_side_liquidity"] = _contains(liquidity_zones, r"buy-side")
    features["sell_side_liquidity"] = _contains(liquidity_zones, r"sell-side")
    features["liquidity_sweep_risk"] = _contains(liquidity_zones, r"sweep")

    features["imbalance_bullish"] = _contains(imbalance_fill, r"bullish")
    features["imbalance_bearish"] = _contains(imbalance_fill, r"bearish")
    features["imbalance_filled"] = _contains(imbalance_fill, r"to'liq|filled")
    features["imbalance_partial"] = _contains(imbalance_fill, r"%")

    features["wyckoff_markup"] = _contains(wyckoff_phase, r"MARKUP")
    features["wyckoff_markdown"] = _contains(wyckoff_phase, r"MARKDOWN")
    features["wyckoff_accum"] = _contains(wyckoff_phase, r"ACCUMULATION")
    features["wyckoff_dist"] = _contains(wyckoff_phase, r"DISTRIBUTION")
    features["wyckoff_ranging"] = _contains(wyckoff_phase, r"RANGING")

    features["structure_bullish"] = _contains(market_structure, r"bullish")
    features["structure_bearish"] = _contains(market_structure, r"bearish")
    features["structure_bos"] = _contains(market_structure, r"\bBOS\b")
    features["structure_ranging"] = _contains(market_structure, r"ranging|compression|mixed")

    features["div_bullish"] = _contains(divergence_text, r"bullish")
    features["div_bearish"] = _contains(divergence_text, r"bearish")
    features["div_hidden"] = _contains(divergence_text, r"hidden")

    features = features.fillna(0)

    for col in features.columns:
        features[col] = pd.to_numeric(features[col], errors="coerce").fillna(0.0)

    return features


# ─────────────────────────────────────────
# Training frame helpers
# ─────────────────────────────────────────
def get_training_frame() -> pd.DataFrame:
    if not JOURNAL_PATH.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(JOURNAL_PATH)
    except Exception:
        return pd.DataFrame()

    if "outcome" not in df.columns or "final_signal" not in df.columns:
        return pd.DataFrame()

    df["outcome"] = df["outcome"].astype(str).str.upper().str.strip()
    df["final_signal"] = df["final_signal"].astype(str).str.upper().str.strip()

    df_model = df[
        df["outcome"].isin(["WIN", "LOSS"]) &
        df["final_signal"].isin(["BUY", "SELL"])
    ].copy()

    if df_model.empty:
        return df_model

    if "candle_time" in df_model.columns:
        df_model["_sort_time"] = pd.to_datetime(df_model["candle_time"], errors="coerce")
    elif "time" in df_model.columns:
        df_model["_sort_time"] = pd.to_datetime(df_model["time"], errors="coerce")
    else:
        df_model["_sort_time"] = pd.RangeIndex(start=0, stop=len(df_model), step=1)

    df_model = df_model.sort_values("_sort_time").reset_index(drop=True)
    return df_model


def get_training_health() -> dict:
    df_model = get_training_frame()

    if df_model.empty:
        return {
            "samples": 0,
            "win_count": 0,
            "loss_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "class_ok": False,
            "ready": False,
        }

    win_count = int((df_model["outcome"] == "WIN").sum())
    loss_count = int((df_model["outcome"] == "LOSS").sum())
    buy_count = int((df_model["final_signal"] == "BUY").sum())
    sell_count = int((df_model["final_signal"] == "SELL").sum())

    samples = len(df_model)
    class_ok = min(win_count, loss_count) >= MIN_CLASS_SAMPLES
    ready = samples >= MIN_SAMPLES and class_ok

    return {
        "samples": samples,
        "win_count": win_count,
        "loss_count": loss_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "class_ok": class_ok,
        "ready": ready,
    }


# ─────────────────────────────────────────
# Model o'qitish
# ─────────────────────────────────────────
def train_model():
    """
    signal_journal.csv dan model o'qitadi.
    Minimum MIN_SAMPLES ta WIN/LOSS kerak.
    """
    print(f"\n{'='*50}")
    print(f"  ML MODEL O'QITILMOQDA")
    print(f"{'='*50}\n")

    df_model = get_training_frame()

    if df_model.empty:
        print("signal_journal.csv topilmadi yoki training frame bo'sh!")
        return None

    health = get_training_health()

    if health["samples"] < MIN_SAMPLES:
        print("Yetarli ma'lumot yo'q!")
        print(f"Hozir: {health['samples']} ta")
        print(f"Kerak: {MIN_SAMPLES} ta")
        print(f"Yana {MIN_SAMPLES - health['samples']} ta signal kerak!")
        return None

    if not health["class_ok"]:
        print("WIN/LOSS balans hali yetarli emas!")
        print(f"WIN:  {health['win_count']} ta")
        print(f"LOSS: {health['loss_count']} ta")
        print(f"Har klasstan kamida {MIN_CLASS_SAMPLES} ta kerak.")
        return None

    X = prepare_features(df_model)
    y = (df_model["outcome"] == "WIN").astype(int)

    if y.nunique() < 2:
        print("Model o'qitish uchun WIN va LOSS ikkalasi ham bo'lishi kerak.")
        return None

    split_idx = int(len(df_model) * 0.8)
    split_idx = max(split_idx, 1)
    split_idx = min(split_idx, len(df_model) - 1)

    X_train = X.iloc[:split_idx].copy()
    X_test = X.iloc[split_idx:].copy()
    y_train = y.iloc[:split_idx].copy()
    y_test = y.iloc[split_idx:].copy()

    print(f"O'qitish uchun ma'lumot: {len(df_model)} ta signal")
    print(f"Train: {len(X_train)} ta | Test: {len(X_test)} ta")
    print(f"WIN:  {health['win_count']} ta")
    print(f"LOSS: {health['loss_count']} ta\n")

    print("Feature audit:")
    print(f"  Feature soni: {len(X.columns)}")
    non_zero_counts = (X != 0).sum().sort_values(ascending=False).head(15)
    for feat, cnt in non_zero_counts.items():
        print(f"  {feat:28s} -> {int(cnt)}")

    try:
        import xgboost as xgb
    except ImportError:
        print("XGBoost o'rnatilmagan!")
        print("O'rnatish: venv\\Scripts\\python.exe -m pip install xgboost scikit-learn")
        return None

    model = xgb.XGBClassifier(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )

    model.fit(X_train, y_train)

    from sklearn.metrics import accuracy_score, classification_report
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print(f"\nModel aniqligi: {acc*100:.1f}%")
    print("\nBatafsil hisobot:")
    print(classification_report(y_test, y_pred, target_names=["LOSS", "WIN"], zero_division=0))

    print("Eng muhim feature lar:")
    importance = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False).head(15)
    for feat, imp in importance.items():
        bar = "█" * int(imp * 50)
        print(f"  {feat:28s} {bar} {imp:.3f}")

    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(
            {
                "model": model,
                "features": list(X.columns),
                "accuracy": acc,
                "trained": pd.Timestamp.now().isoformat(),
                "samples": len(df_model),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "win_count": health["win_count"],
                "loss_count": health["loss_count"],
                "min_samples_required": MIN_SAMPLES,
                "min_class_samples_required": MIN_CLASS_SAMPLES,
                "version": MODEL_VERSION,
            },
            f,
        )

    print(f"\nModel saqlandi: {MODEL_PATH}")
    print(f"{'='*50}\n")

    return model


# ─────────────────────────────────────────
# Model yuklash
# ─────────────────────────────────────────
def load_model_bundle():
    if not MODEL_PATH.exists():
        return None

    try:
        with open(MODEL_PATH, "rb") as f:
            data = pickle.load(f)
    except Exception as e:
        print(f"Model yuklanmadi: {e}")
        return None

    required_keys = {"model", "features"}
    if not required_keys.issubset(set(data.keys())):
        print("Model bundle format noto'g'ri.")
        return None

    return data


def load_model():
    """
    Backward-compatible loader.
    """
    bundle = load_model_bundle()
    if bundle is None:
        return None, None
    return bundle["model"], bundle["features"]


def get_training_sample_count() -> int:
    """
    WIN/LOSS bilan yakunlangan BUY/SELL signal sample lar sonini qaytaradi.
    """
    return get_training_health()["samples"]


# ─────────────────────────────────────────
# Signal filtri
# ─────────────────────────────────────────
def ml_filter(result: dict) -> tuple:
    """
    Yangi signal uchun ML ehtimollik hisoblaydi.

    Qaytaradi:
      (approved: bool, probability: float, reason: str)
    """
    final_signal = str(result.get("final_signal", "")).upper().strip()

    # WAIT / NO_TRADE uchun ML gate kerak emas
    if final_signal not in ["BUY", "SELL"]:
        return True, 0.0, "ML skip: actionable BUY/SELL signal yo'q"

    bundle = load_model_bundle()

    if bundle is None:
        return True, 0.0, "ML model hali o'qitilmagan"

    if bundle.get("version") != MODEL_VERSION:
        return True, 0.0, "ML model versiyasi eskirgan, filter skip qilindi"

    samples = int(bundle.get("samples", 0))
    win_count = int(bundle.get("win_count", 0))
    loss_count = int(bundle.get("loss_count", 0))

    if samples < MIN_SAMPLES:
        return True, 0.0, "ML model sample soni yetarli emas"

    if min(win_count, loss_count) < MIN_CLASS_SAMPLES:
        return True, 0.0, "ML model class balans hali yetarli emas"

    model = bundle["model"]
    feature_names = bundle["features"]

    row_df = pd.DataFrame([result])
    X = prepare_features(row_df)

    for feat in feature_names:
        if feat not in X.columns:
            X[feat] = 0.0

    X = X[feature_names]

    try:
        prob = model.predict_proba(X)[0][1]
    except Exception as e:
        return True, 0.0, f"ML xato: {e}"

    approved = prob >= MIN_PROB
    reason = (
        f"ML: {prob*100:.1f}% WIN ehtimoli "
        f"({'✅ RUXSAT' if approved else '❌ BLOKLASH'})"
    )

    return approved, round(float(prob), 3), reason


# ─────────────────────────────────────────
# Ishga tushirish
# ─────────────────────────────────────────
def print_ml_readiness():
    print(f"\n{'='*50}")
    print("  ML LIVE ENABLEMENT CHECKLIST")
    print(f"{'='*50}\n")

    if not JOURNAL_PATH.exists():
        print("signal_journal.csv topilmadi!")
        return

    health = get_training_health()

    print(f"Journal: {JOURNAL_PATH}")
    print(f"BUY/SELL sample: {health['samples']}")
    print(f"BUY count:       {health['buy_count']}")
    print(f"SELL count:      {health['sell_count']}")
    print(f"WIN count:       {health['win_count']}")
    print(f"LOSS count:      {health['loss_count']}")
    print(f"Min sample req:  {MIN_SAMPLES}")
    print(f"Min class req:   {MIN_CLASS_SAMPLES}")

    if health["ready"]:
        print("\nSTATUS: ML ni yoqish mumkin ✅")
    else:
        print("\nSTATUS: Hali ML ni yoqish mumkin emas ⛔")

        if health["samples"] < MIN_SAMPLES:
            print(f"- Yana {MIN_SAMPLES - health['samples']} ta WIN/LOSS kerak")

        if not health["class_ok"]:
            shortage = MIN_CLASS_SAMPLES - min(health["win_count"], health["loss_count"])
            if shortage > 0:
                print(f"- WIN/LOSS balans uchun yana kamida {shortage} ta kerak")

    print(f"\n{'='*50}\n")


if __name__ == "__main__":
    print_ml_readiness()
    train_model()