"""Daily gold (XAU/USD) outlook: key levels, where liquidity rests, and a rule-based bias for
the next hour, the next 4 hours and the day.

Deterministic: every level and bias comes from hourly prices with fixed rules (EMAs, market
structure, prior-day / Asian-session / weekly ranges, liquidity sweeps, ATR ranges, dollar and
real-yield tilt). The script writer only narrates this; it never invents a number or a call.
"""
from datetime import datetime, timedelta, timezone

ASIA_END_HOUR = 6  # UTC; the Asian range (00:00-06:00) is what London usually tests first


# ─── helpers ───────────────────────────────────────────────────────────────

def _bars(gold: dict) -> list[dict]:
    return [{"t": datetime.fromisoformat(t), "o": o, "h": h, "l": lo, "c": c} for t, o, h, lo, c in gold["bars"]]


def _ema(vals: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for v in vals:
        out.append(v if not out else out[-1] + k * (v - out[-1]))
    return out


def _rsi(closes: list[float], n: int = 14) -> float:
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    return 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)


def _atr(bars: list[dict], n: int = 14) -> float:
    trs = [max(b["h"] - b["l"], abs(b["h"] - a["c"]), abs(b["l"] - a["c"])) for a, b in zip(bars, bars[1:])]
    trs = trs[-n:]
    return sum(trs) / len(trs) if trs else 0.0


def _group(bars: list[dict], key) -> list[dict]:
    out, cur, k0 = [], None, None
    for b in bars:
        k = key(b["t"])
        if k != k0:
            if cur:
                out.append(cur)
            cur, k0 = dict(b, k=k), k
        else:
            cur["h"], cur["l"], cur["c"] = max(cur["h"], b["h"]), min(cur["l"], b["l"]), b["c"]
    if cur:
        out.append(cur)
    return out


def _weekday(t: datetime) -> bool:
    return t.weekday() < 5


def _swings(bars: list[dict], k: int = 2) -> tuple[list[float], list[float]]:
    highs, lows = [], []
    for i in range(k, len(bars) - k):
        win = bars[i - k:i + k + 1]
        if bars[i]["h"] == max(b["h"] for b in win):
            highs.append(bars[i]["h"])
        if bars[i]["l"] == min(b["l"] for b in win):
            lows.append(bars[i]["l"])
    return highs, lows


def _label(score: float) -> str:
    return "bullish" if score >= 1.5 else "bearish" if score <= -1.5 else "neutral"


def _strength(score: float, top: float) -> str:
    r = abs(score) / top
    return "strong" if r >= 0.7 else "moderate" if r >= 0.4 else "weak"


def _trend(bars: list[dict], name: str) -> dict:
    """EMA 20/50 + structure + RSI for one timeframe → score and plain-English reasons."""
    closes = [b["c"] for b in bars]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    price, score, reasons = closes[-1], 0.0, []
    if price > e20[-1]:
        score += 1
        reasons.append("price above the 20 EMA")
    else:
        score -= 1
        reasons.append("price below the 20 EMA")
    if e20[-1] > e50[-1]:
        score += 1
        reasons.append("20 EMA above the 50 EMA")
    else:
        score -= 1
        reasons.append("20 EMA below the 50 EMA")
    slope = e20[-1] - e20[-4]
    score += 0.5 if slope > 0 else -0.5
    highs, lows = _swings(bars[-40:])
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            score += 1
            reasons.append("higher highs and higher lows")
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            score -= 1
            reasons.append("lower highs and lower lows")
    rsi = _rsi(closes)
    if rsi >= 70:
        score -= 0.5
        reasons.append(f"RSI {rsi:.0f}, stretched to the upside")
    elif rsi <= 30:
        score += 0.5
        reasons.append(f"RSI {rsi:.0f}, stretched to the downside")
    return {"timeframe": name, "bias": _label(score), "strength": _strength(score, 3.5), "score": round(score, 2),
            "reasons": reasons, "ema20": round(e20[-1], 1), "ema50": round(e50[-1], 1), "rsi": round(rsi)}


def _merge_levels(levels: list[tuple[float, str]], price: float, above: bool, tol: float = 0.0012) -> list[dict]:
    """Nearest levels on one side of price; levels within ~0.12% of each other are one zone."""
    side = sorted((lv for lv in levels if (lv[0] > price if above else lv[0] < price)),
                  key=lambda lv: abs(lv[0] - price))
    out: list[dict] = []
    for p, name in side:
        for z in out:
            if abs(z["price"] - p) / price <= tol:
                if name not in z["labels"]:
                    z["labels"].append(name)
                break
        else:
            out.append({"price": round(p, 1), "labels": [name]})
    for z in out:
        z["distance_pct"] = round((z["price"] / price - 1) * 100, 2)
        z["label"] = " + ".join(z["labels"][:2])
    return out[:6]


# ─── the outlook ───────────────────────────────────────────────────────────

def analyze(data: dict, previous: dict | None = None, now: datetime | None = None) -> dict:
    """previous: the last gold outlook from history (for the "yesterday's call" check)."""
    now = now or datetime.now(timezone.utc)
    bars = _bars(data["gold"])
    price = bars[-1]["c"]
    today = now.date()

    # ranges: previous trading day, today's Asian session, this week and last week (weekdays only)
    days = [d for d in _group([b for b in bars if _weekday(b["t"])], lambda t: t.date())]
    past_days = [d for d in days if d["k"] < today]
    if len(past_days) < 5:
        raise RuntimeError("Not enough gold history for an outlook")
    prev = past_days[-1]
    today_bars = [b for b in bars if b["t"].date() == today]
    asia = [b for b in today_bars if b["t"].hour < ASIA_END_HOUR]
    week_key = lambda t: t.isocalendar()[:2]  # noqa: E731
    this_week = [b for b in bars if _weekday(b["t"]) and week_key(b["t"]) == week_key(now)]
    last_week = [b for b in bars if _weekday(b["t"]) and week_key(b["t"]) == week_key(now - timedelta(days=7))]

    levels: list[tuple[float, str]] = [(prev["h"], "previous day high"), (prev["l"], "previous day low")]
    if asia:
        levels += [(max(b["h"] for b in asia), "Asian session high"), (min(b["l"] for b in asia), "Asian session low")]
    if this_week and this_week[0]["t"].date() < today:
        levels += [(max(b["h"] for b in this_week), "this week's high"), (min(b["l"] for b in this_week), "this week's low")]
    if last_week:
        levels += [(max(b["h"] for b in last_week), "last week's high"), (min(b["l"] for b in last_week), "last week's low")]
    # equal highs / lows on the hourly chart (last 3 days): stop orders tend to rest just beyond them
    highs, lows = _swings(bars[-72:], k=3)
    for pts, name, side in ((highs, "equal highs", 1), (lows, "equal lows", -1)):
        for a, b in zip(pts, pts[1:]):
            mid = (a + b) / 2
            if abs(a - b) / price <= 0.0008 and (mid - price) * side > 0:  # highs above, lows below
                levels.append((mid, name))
    step = 50
    base = int(price // step) * step
    levels += [(base, f"round number ${base:,}"), (base + step, f"round number ${base + step:,}")]

    above_all = _merge_levels(levels, price, above=True)
    below_all = _merge_levels(levels, price, above=False)
    above, below = above_all[:3], below_all[:3]

    # liquidity sweeps today: took out a prior high/low, then came back inside = a classic reversal tell
    sweeps = []
    if today_bars:
        hi, lo = max(b["h"] for b in today_bars), min(b["l"] for b in today_bars)
        if hi > prev["h"] and price < prev["h"]:
            sweeps.append({"level": round(prev["h"], 1), "name": "previous day high", "type": "swept and rejected"})
        if lo < prev["l"] and price > prev["l"]:
            sweeps.append({"level": round(prev["l"], 1), "name": "previous day low", "type": "swept and reclaimed"})

    # timeframe biases
    h1 = _trend(bars[-200:], "1H")
    four = _group(bars, lambda t: (t.date(), t.hour // 4))
    h4 = _trend(four[-120:], "4H")

    d_score, d_reasons = 0.0, []
    if price > prev["h"]:
        d_score += 1.5
        d_reasons.append("trading above the previous day's high")
    elif price < prev["l"]:
        d_score -= 1.5
        d_reasons.append("trading below the previous day's low")
    else:
        mid = (prev["h"] + prev["l"]) / 2
        d_score += 0.5 if price > mid else -0.5
        d_reasons.append(f"inside the previous day's range, {'upper' if price > mid else 'lower'} half")
    dcloses = [d["c"] for d in days]
    if len(dcloses) >= 10:
        e20 = _ema(dcloses, 20)
        d_score += 1 if price > e20[-1] else -1
        d_reasons.append(f"{'above' if price > e20[-1] else 'below'} the daily 20 EMA")
    d_score += 0.5 * (1 if h4["bias"] == "bullish" else -1 if h4["bias"] == "bearish" else 0)
    for s in sweeps:
        d_score += 1 if s["type"] == "swept and reclaimed" else -1
        d_reasons.append(f"{s['name']} {s['type']}")
    fx = data.get("fx", {})
    usd_vals = [f["change_1d"] if p.startswith("USD") else -f["change_1d"] for p, f in fx.items()]
    usd = sum(usd_vals) / len(usd_vals) if usd_vals else None
    if usd is not None and abs(usd) >= 0.3:
        d_score += -0.5 if usd > 0 else 0.5
        d_reasons.append(f"dollar {'stronger' if usd > 0 else 'weaker'} on the day")
    real = data.get("macro", {}).get("us10y_real")
    if real and abs(real["change_bp"]) >= 5:
        d_score += -0.5 if real["change_bp"] > 0 else 0.5
        d_reasons.append(f"real yields {'up' if real['change_bp'] > 0 else 'down'} {abs(real['change_bp'])} bp")
    daily = {"timeframe": "Daily", "bias": _label(d_score), "strength": _strength(d_score, 5), "score": round(d_score, 2),
             "reasons": d_reasons}

    # ranges: typical moves (ATR) for each horizon, and today's projected range (ADR)
    atr1, atr4 = _atr(bars[-30:]), _atr(four[-30:])
    adr = _atr(past_days[-15:])
    t_hi = max((b["h"] for b in today_bars), default=price)
    t_lo = min((b["l"] for b in today_bars), default=price)
    proj_hi, proj_lo = max(t_hi, t_lo + adr), min(t_lo, t_hi - adr)

    # scenarios: the nearest liquidity on each side is the trigger; the objective is the next level
    # at least ~0.6x a typical 4-hour move beyond it (else the edge of today's typical range)
    def objective(trigger, side, edge, edge_name):
        far = [z for z in side if abs(z["price"] - trigger["price"]) >= 0.6 * atr4]
        if far:
            return far[0]
        if abs(edge - trigger["price"]) >= 0.6 * atr4:
            return {"price": round(edge, 1), "labels": [edge_name], "label": edge_name,
                    "distance_pct": round((edge / price - 1) * 100, 2)}
        return None
    r1 = above_all[0] if above_all else None
    s1 = below_all[0] if below_all else None
    bull = {"trigger": r1, "objective": objective(r1, above_all[1:], proj_hi, "top of today's typical range")} \
        if r1 else None
    bear = {"trigger": s1, "objective": objective(s1, below_all[1:], proj_lo, "bottom of today's typical range")} \
        if s1 else None
    invalidation = (s1 if daily["bias"] == "bullish" else r1 if daily["bias"] == "bearish" else None)

    events = []
    for ev in data.get("calendar", []):
        if ev.get("currency") == "USD":
            try:
                when = datetime.fromisoformat(ev["datetime"])
            except (KeyError, ValueError):
                continue
            if now - timedelta(hours=1) <= when <= now + timedelta(hours=20):
                events.append({"time_utc": ev["time_utc"], "event": ev["event"]})

    review = None
    if previous and previous.get("price") and previous.get("daily_bias"):
        try:
            then = datetime.fromisoformat(previous["time"])
        except (KeyError, ValueError):
            then = None
        if then and timedelta(hours=12) <= now - then <= timedelta(days=4):
            chg = (price / previous["price"] - 1) * 100
            b = previous["daily_bias"]
            hit = (b == "bullish" and chg > 0.15) or (b == "bearish" and chg < -0.15) or \
                  (b == "neutral" and abs(chg) < 0.5)
            review = {"bias": b, "price_then": round(previous["price"], 1), "price_now": round(price, 1),
                      "change_pct": round(chg, 2), "played_out": hit, "date": then.strftime("%b %d")}

    return {
        "price": round(price, 1), "change_24h_pct": round(data["gold"]["change_24h"], 2),
        "change_7d_pct": round(data["gold"]["change_7d"], 2),
        "previous_day": {"high": round(prev["h"], 1), "low": round(prev["l"], 1), "close": round(prev["c"], 1),
                         "date": prev["k"].isoformat()},
        "asian_session": ({"high": round(max(b["h"] for b in asia), 1), "low": round(min(b["l"] for b in asia), 1)}
                          if asia else None),
        "today": {"high": round(t_hi, 1), "low": round(t_lo, 1)},
        "liquidity_above": above, "liquidity_below": below, "sweeps": sweeps,
        "bias": {"1H": h1, "4H": h4, "Daily": daily},
        "typical_move": {"next_1h": round(atr1, 1), "next_4h": round(atr4, 1), "daily_range": round(adr, 1)},
        "projected_range": {"low": round(proj_lo, 1), "high": round(proj_hi, 1)},
        "scenarios": {"bull": bull, "bear": bear}, "invalidation": invalidation,
        "usd_change_1d_pct": round(usd, 2) if usd is not None else None,
        "events_usd": events[:3], "review": review,
        "method": "Rule-based technical read of hourly XAU/USD: EMA 20/50 trend, swing structure, RSI, "
                  "prior-day/Asian/weekly ranges, equal highs/lows, sweeps, ATR ranges, dollar and real-yield tilt.",
    }


def record(analysis: dict) -> dict:
    """What history keeps so tomorrow's video can say whether today's call played out."""
    return {"price": analysis["price"], "daily_bias": analysis["bias"]["Daily"]["bias"],
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
