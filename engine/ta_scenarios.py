"""차트 기술적 분석으로 만든 미래 시나리오 2개(주 시나리오·대안 시나리오)와 가상 캔들.

통계 모델(fan)과 달리 '차트 모양'만으로 경로를 그린다. 고전 기술적 분석의 규칙을 그대로 코드로 옮겼다.

참고한 기법
- 다우 이론: 고점·저점이 높아지면(HH·HL) 상승 추세, 낮아지면(LH·LL) 하락 추세. 직전 저점(고점)을 깨면 추세 무효.
- 지그재그 스윙: ATR의 일정 배수 이상 움직인 고점·저점만 '의미 있는 스윙'으로 본다.
- 지지·저항과 역할 전환: 과거 스윙 고점·저점이 몰린 가격대. 돌파한 저항은 지지가 된다(되돌림 때 재시험).
- 피보나치 되돌림(38.2~61.8%): 추세 중 눌림이 멈추기 쉬운 구간. 지지와 겹치는 가격을 우선.
- 측정 이동(AB=CD)과 피보나치 확장(1.618): 직전 파동 폭만큼 다음 파동이 간다고 보는 목표가.
- 이동평균 배열·MACD·RSI·볼린저·거래량: 추세 방향의 근거 점수(어느 쪽 시나리오가 '주'인지 결정).

경로의 리듬(파동 하나의 폭·걸리는 봉 수·되돌림 비율)은 그 봉의 최근 스윙 통계에서 가져오므로
과거 차트처럼 오르내림이 있는 캔들이 나온다. 확률 모델이 아니므로 '확률' 대신 근거 비중과
백테스트(주 시나리오의 첫 목표가 무효화 가격보다 먼저 닿은 비율 vs 무작위 기준)를 함께 낸다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# horizon: 그릴 미래 봉 수, zz: 지그재그 문턱(ATR 배수), look: 스윙을 찾을 과거 봉 수
# bt_h/bt_step: 백테스트 확인 기간·간격(봉), bt_from: 백테스트 시작 봉 수
TF_CFG = {
    "1h": {"horizon": 720, "zz": 3.0, "look": 1500, "bt_h": 168, "bt_step": 4, "bt_from": 500},
    "4h": {"horizon": 180, "zz": 3.0, "look": 1500, "bt_h": 84, "bt_step": 3, "bt_from": 400},
    "1d": {"horizon": 30, "zz": 2.5, "look": 1000, "bt_h": 30, "bt_step": 3, "bt_from": 500},
    "1w": {"horizon": 53, "zz": 2.0, "look": None, "bt_h": 26, "bt_step": 2, "bt_from": 120},
    "1M": {"horizon": 61, "zz": 1.5, "look": None, "bt_h": None, "bt_step": None, "bt_from": None},
}
FIB_ZONE = (0.382, 0.618)
RETR_CYCLE = (0.5, 0.382, 0.618)   # 충격파 뒤 되돌림 비율을 번갈아 사용(얕은·깊은 조정 교대)
MAX_TARGETS = 3
STEP_SEC = {"1h": 3600, "4h": 14400, "1d": 86400, "1w": 7 * 86400}
TOPIC_KO = {"up": "상승", "down": "하락", "range": "박스권"}


# ───────────────────────── 스윙 구조 ─────────────────────────
def zigzag(high: np.ndarray, low: np.ndarray, thr: np.ndarray) -> tuple[list, int, int]:
    """로그가격 지그재그. thr[i] = i번째 봉에서 반전으로 인정할 최소 로그 폭.

    반환: (확정 피벗 [(i, 로그가격, +1 고점/-1 저점)], 진행 중 파동 방향(+1/-1/0), 진행 중 극값 위치)
    i번째 봉까지만 보고 확정하므로 미래 정보를 쓰지 않는다.
    """
    lh, ll = np.log(high), np.log(low)
    piv: list = []
    d, hi_i, lo_i = 0, 0, 0
    for i in range(1, len(lh)):
        t = thr[i]
        if d == 0:
            if lh[i] > lh[hi_i]:
                hi_i = i
            if ll[i] < ll[lo_i]:
                lo_i = i
            if lh[hi_i] - ll[lo_i] >= t:
                if hi_i > lo_i:
                    piv.append((lo_i, ll[lo_i], -1)); d = 1
                else:
                    piv.append((hi_i, lh[hi_i], 1)); d = -1
        elif d == 1:
            if lh[i] >= lh[hi_i]:
                hi_i = i
            elif lh[hi_i] - ll[i] >= t:
                piv.append((hi_i, lh[hi_i], 1)); d = -1; lo_i = i
        else:
            if ll[i] <= ll[lo_i]:
                lo_i = i
            elif lh[i] - ll[lo_i] >= t:
                piv.append((lo_i, ll[lo_i], -1)); d = 1; hi_i = i
    ext = hi_i if d == 1 else lo_i
    return piv, d, ext


def swing_stats(piv: list, sigma: float) -> dict:
    """최근 스윙(최대 30개)의 폭·속도·되돌림 비율 중앙값."""
    legs = [(b[1] - a[1], b[0] - a[0]) for a, b in zip(piv[:-1], piv[1:])][-30:]
    up = [(a, n) for a, n in legs if a > 0]
    dn = [(-a, n) for a, n in legs if a < 0]
    fallback_amp = 6 * sigma
    amp_up = float(np.median([a for a, _ in up])) if len(up) >= 2 else fallback_amp
    amp_dn = float(np.median([a for a, _ in dn])) if len(dn) >= 2 else fallback_amp
    spd = lambda arr, amp: float(np.median([a / max(n, 1) for a, n in arr])) if len(arr) >= 2 else amp / 8  # noqa: E731
    ratios = [abs(b[0]) / abs(a[0]) for a, b in zip(legs[:-1], legs[1:]) if abs(a[0]) > 0]
    retr = float(np.clip(np.median(ratios), 0.35, 0.75)) if len(ratios) >= 3 else 0.5
    return {"amp_up": amp_up, "amp_dn": amp_dn, "spd_up": spd(up, amp_up), "spd_dn": spd(dn, amp_dn),
            "retr": retr, "n_legs": len(legs),
            "bars_med": float(np.median([n for _, n in legs])) if legs else None}


def find_levels(piv: list, atr_rel: float, cur: float) -> list[dict]:
    """스윙 피벗을 가격대로 묶은 지지/저항(로그가격). 최근·여러 번 닿을수록 강함."""
    if not piv:
        return []
    last_i = piv[-1][0]
    pts = sorted(piv, key=lambda p: p[1])
    tol = 0.6 * atr_rel
    groups: list[list] = []
    for p in pts:
        if groups and p[1] - groups[-1][0][1] <= tol:
            groups[-1].append(p)
        else:
            groups.append([p])
    out = []
    span = max(last_i - piv[0][0], 1)
    for g in groups:
        w = np.array([0.5 + (p[0] - piv[0][0]) / span for p in g])  # 최근 피벗일수록 가중
        lv = float(np.average([p[1] for p in g], weights=w))
        out.append({"log": lv, "touches": len(g), "score": float(w.sum()), "src": "level"})
    smax = max(o["score"] for o in out)
    for o in out:
        o["strength"] = o.pop("score") / smax
        o["note"] = f"{'저항' if o['log'] > cur else '지지'}(스윙 {o['touches']}회)"
    return out


def structure(piv: list) -> dict:
    """다우 이론 구조: 마지막 두 고점·두 저점 비교."""
    hs = [p for p in piv if p[2] == 1][-2:]
    ls = [p for p in piv if p[2] == -1][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return {"code": "unknown", "label_ko": "스윙이 부족해 판단 보류", "signal": 0}
    hh, hl = hs[1][1] > hs[0][1], ls[1][1] > ls[0][1]
    if hh and hl:
        return {"code": "HH_HL", "label_ko": "고점·저점이 함께 높아지는 중(상승 구조)", "signal": 1}
    if not hh and not hl:
        return {"code": "LH_LL", "label_ko": "고점·저점이 함께 낮아지는 중(하락 구조)", "signal": -1}
    if hh:
        return {"code": "HH_LL", "label_ko": "고점은 높아졌지만 저점은 낮아짐(확산·혼조)", "signal": 0}
    return {"code": "LH_HL", "label_ko": "고점은 낮아지고 저점은 높아짐(수렴·삼각형)", "signal": 0}


# ───────────────────────── 근거 점수 ─────────────────────────
def evidence(df: pd.DataFrame, ind: pd.DataFrame, struct: dict) -> dict:
    last = ind.iloc[-1]
    c = float(df["close"].iloc[-1])
    items = []

    def add(key, name, sig, text):
        items.append({"key": key, "name_ko": name, "signal": int(sig), "text_ko": text})

    s20, s50, s200 = (float(last[k]) for k in ("sma20", "sma50", "sma200"))
    if not math.isnan(s200):
        if s20 > s50 > s200:
            add("ma_stack", "이동평균 배열", 1, "20>50>200 정배열")
        elif s20 < s50 < s200:
            add("ma_stack", "이동평균 배열", -1, "20<50<200 역배열")
        else:
            add("ma_stack", "이동평균 배열", 0, "배열이 섞여 있음")
    elif not math.isnan(s50):
        add("ma_stack", "이동평균 배열", 1 if s20 > s50 else -1, f"20선이 50선 {'위' if s20 > s50 else '아래'}")
    if not math.isnan(s50):
        add("price_ma50", "가격 vs 50선", 1 if c > s50 else -1, f"가격이 50선 {'위' if c > s50 else '아래'}")
        prev = ind["sma50"].iloc[-11] if len(ind) > 60 else float("nan")
        if not math.isnan(prev):
            sl = s50 / prev - 1
            add("ma50_slope", "50선 기울기", 1 if sl > 0.003 else -1 if sl < -0.003 else 0,
                f"10봉 {'상승' if sl > 0.003 else '하락' if sl < -0.003 else '평탄'}({sl * 100:+.1f}%)")
    add("dow", "고점·저점 구조", struct["signal"], struct["label_ko"])
    h, h_prev = float(last["hist"]), float(ind["hist"].iloc[-4])
    if not math.isnan(h):
        sig = 1 if h > 0 and h >= h_prev else -1 if h < 0 and h <= h_prev else 0
        add("macd", "MACD", sig, f"히스토그램 {'플러스' if h > 0 else '마이너스'}, {'커지는' if abs(h) >= abs(h_prev) else '줄어드는'} 중")
    r = float(last["rsi14"])
    if not math.isnan(r):
        sig = 1 if 55 <= r < 75 else -1 if 25 < r <= 45 else 0
        extra = " · 과매수(되돌림 주의)" if r >= 70 else " · 과매도(반등 주의)" if r <= 30 else ""
        add("rsi", "RSI", sig, f"{r:.0f}{extra}")
    mid = float(last["bb_mid"])
    if not math.isnan(mid):
        add("bb_mid", "볼린저 중심선", 1 if c > mid else -1, f"가격이 중심선 {'위' if c > mid else '아래'}")
    tail = df.iloc[-20:]
    upv = float(tail.loc[tail["close"] >= tail["open"], "volume"].sum())
    dnv = float(tail.loc[tail["close"] < tail["open"], "volume"].sum())
    if upv + dnv > 0:
        ratio = upv / (upv + dnv)
        add("volume", "거래량 쏠림", 1 if ratio > 0.55 else -1 if ratio < 0.45 else 0,
            f"최근 20봉 거래량 중 양봉 {ratio * 100:.0f}%")
    bull = sum(1 for i in items if i["signal"] > 0)
    bear = sum(1 for i in items if i["signal"] < 0)
    return {"items": items, "bull": bull, "bear": bear, "neutral": len(items) - bull - bear,
            "score": round((bull - bear) / max(len(items), 1), 3)}


# ───────────────────────── 경로(파동) 설계 ─────────────────────────
class _Builder:
    """로그가격 경유점(봉 위치, 가격, 설명)을 쌓는다."""

    def __init__(self, ctx: dict, direction: int):
        self.c = ctx
        self.d = direction
        self.pts = [(0, ctx["cur"], "현재", "start")]

    @property
    def pos(self):
        return self.pts[-1][1]

    @property
    def bar(self):
        return self.pts[-1][0]

    def leg(self, to: float, note: str, kind: str):
        st = self.c["stats"]
        amp = to - self.pos
        spd = st["spd_up"] if amp > 0 else st["spd_dn"]
        n = max(2, int(round(abs(amp) / max(spd, 1e-6))))
        self.pts.append((self.bar + n, to, note, kind))

    def done(self):
        return self.bar >= self.c["H"]


def _ladder(ctx: dict, d: int, start: float, extra: list[dict]) -> list[dict]:
    """방향 d로 가는 길의 목표가 사다리: 지지/저항 + 측정 이동 + 피보나치 확장. 가까운 순."""
    atr, maxd = ctx["atr_rel"], ctx["maxdist"]
    cands = [lv for lv in ctx["levels"] if 0.5 * atr < d * (lv["log"] - start) <= maxd] + \
            [e for e in extra if 0.5 * atr < d * (e["log"] - start) <= maxd]
    cands.sort(key=lambda x: d * (x["log"] - start))
    groups: list[list[dict]] = []
    for cnd in cands:
        if groups and abs(cnd["log"] - groups[-1][0]["log"]) < 0.6 * atr:
            groups[-1].append(cnd)
        else:
            groups.append([cnd])
    out = []
    kind = "저항" if d > 0 else "지지"
    for g in groups:
        touches = sum(x.get("touches", 0) for x in g if x["src"] == "level")
        tags = ([f"{kind}(스윙 {touches}회)"] if touches else []) +                list(dict.fromkeys(x["note"] for x in g if x["src"] != "level"))
        best = max(g, key=lambda x: x.get("strength", 0))
        out.append({**best, "note": "·".join(tags), "confluence": len(g)})
    return out


def _projections(ctx: dict, d: int) -> list[dict]:
    """직전 같은 방향 파동(A→B) 폭을 다음 출발점(C)에서 투사: 측정 이동(1.0)·피보나치 확장(1.618)."""
    piv = ctx["piv"]
    same = [(a, b) for a, b in zip(piv[:-1], piv[1:]) if d * (b[1] - a[1]) > 0]
    if not same:
        return []
    a, b = same[-1]
    amp = abs(b[1] - a[1])
    # C = 그 파동 뒤 마지막 반대 방향 극점(진행 중 극값 포함)
    c_log = ctx["ext_log"] if ctx["cur_dir"] == -d else (piv[-1][1] if piv[-1][2] == -d else a[1])
    return [{"log": c_log + d * amp, "note": "측정 이동(직전 파동 폭)", "src": "mm", "strength": 0.6},
            {"log": c_log + d * 1.618 * amp, "note": "피보나치 1.618 확장", "src": "fib", "strength": 0.5}]


def _pullback(ctx: dict, d: int) -> tuple[float, str] | None:
    """현재 파동이 d와 반대(되돌림 중)이면 되돌림이 멈출 가격: 피보나치 38.2~61.8% 안의 지지 우선."""
    if ctx["cur_dir"] != -d:
        return None
    piv = ctx["piv"]
    same = [(a, b) for a, b in zip(piv[:-1], piv[1:]) if d * (b[1] - a[1]) > 0]
    cur = ctx["cur"]
    atr = ctx["atr_rel"]
    if same:
        a, b = same[-1]
        amp = b[1] - a[1]
        lo_z, hi_z = b[1] - FIB_ZONE[0] * amp, b[1] - FIB_ZONE[1] * amp  # d=+1: lo_z > hi_z(가격상)
        zone = sorted([lo_z, hi_z])
        lvls = [lv for lv in ctx["levels"] if zone[0] - 0.3 * atr <= lv["log"] <= zone[1] + 0.3 * atr
                and d * (cur - lv["log"]) > 0.3 * atr]
        if lvls:
            best = max(lvls, key=lambda x: x["strength"])
            ratio = (b[1] - best["log"]) / amp
            return best["log"], f"{best['note']} + 피보나치 {ratio * 100:.0f}% 되돌림 겹침"
        for r in (0.5, 0.618):
            p = b[1] - r * amp
            if d * (cur - p) > 0.3 * atr:
                return p, f"피보나치 {r * 100:.1f}% 되돌림"
    st = ctx["stats"]
    return cur - d * 0.3 * (st["amp_up"] if d > 0 else st["amp_dn"]), "짧은 추가 되돌림"


def build_trend(ctx: dict, d: int, label_first: str | None = None) -> dict:
    """추세 시나리오(d=+1 상승, -1 하락): 눌림 → 목표가 사다리를 따라 충격파·되돌림 반복 → 마지막 목표 뒤 횡보."""
    st, atr = ctx["stats"], ctx["atr_rel"]
    amp_d = st["amp_up"] if d > 0 else st["amp_dn"]
    b = _Builder(ctx, d)
    pb = ctx.get("pullback_override") if ctx["cur_dir"] == -d else None
    pb = pb or _pullback(ctx, d)
    if pb:
        b.leg(pb[0], label_first or pb[1], "pullback")
    extra = _projections(ctx, d)
    if ctx.get("break_level") is not None:
        extra.append({"log": ctx["break_level"][0], "note": ctx["break_level"][1], "src": "break", "strength": 1.0})
    ladder = _ladder(ctx, d, max(ctx["cur"], b.pos) if d > 0 else min(ctx["cur"], b.pos), extra)[:MAX_TARGETS]
    if not ladder:
        base = max(ctx["cur"], b.pos) if d > 0 else min(ctx["cur"], b.pos)
        ladder = [{"log": base + d * amp_d, "note": "평균 파동 폭만큼", "src": "amp", "strength": 0.3}]
    first_target = ladder[0]
    targets_hit = []
    imp_start = b.pos
    nretr = 0

    def retr():
        nonlocal nretr
        nretr += 1
        return RETR_CYCLE[(nretr - 1) % len(RETR_CYCLE)]
    for tgt in ladder:
        if b.done():
            break
        # 한 번에 가기엔 먼 목표: 평균 파동 폭만큼 오른 뒤 되돌림을 끼운다
        while d * (tgt["log"] - b.pos) > 1.7 * amp_d and not b.done():
            mid = b.pos + d * amp_d
            b.leg(mid, "중간 파동", "impulse")
            r = retr()
            b.leg(mid - d * r * amp_d, f"피보나치 {r * 100:.1f}% 되돌림", "correction")
            imp_start = b.pos
        if b.done():
            break
        kind = "저항" if d > 0 else "지지"
        b.leg(tgt["log"], f"목표: {tgt['note']}", "target")
        targets_hit.append(tgt)
        # 목표 도달 뒤 되돌림: 방금 돌파한 가격대가 있으면 그곳을 재시험(역할 전환)
        wave = tgt["log"] - imp_start
        r = retr()
        retr_p = tgt["log"] - r * wave
        broken = [x for x in targets_hit[:-1] if abs(x["log"] - retr_p) <= 0.6 * abs(wave)
                  and d * (tgt["log"] - x["log"]) > 0.5 * atr]
        if broken:
            b.leg(broken[-1]["log"], f"돌파한 {kind} 재시험({'저항→지지' if d > 0 else '지지→저항'} 역할 전환)", "retest")
        else:
            b.leg(retr_p, f"피보나치 {r * 100:.1f}% 되돌림", "correction")
        imp_start = b.pos
    # 사다리를 다 쓰면 마지막 목표와 되돌림 사이 박스권(폭이 점점 줄어듦)
    if not b.done() and len(b.pts) >= 2:
        hi_p, lo_p = b.pts[-2][1], b.pts[-1][1]
        k = 0.85
        while not b.done():
            amp = (hi_p - lo_p) * k
            b.leg(lo_p + amp, "목표 뒤 횡보", "range")
            k *= 0.85
            amp = (hi_p - lo_p) * k
            b.leg(hi_p - amp, "목표 뒤 횡보", "range")
            k *= 0.85
    # 무효화: 상승이면 직전 스윙 저점(또는 첫 눌림 아래), 하락이면 직전 스윙 고점
    opp = [p for p in ctx["piv"] if p[2] == -d]
    inv = opp[-1][1] if opp else ctx["cur"] - d * amp_d
    first_low = b.pts[1][1] if len(b.pts) > 1 and b.pts[1][3] == "pullback" else ctx["cur"]
    edge = min(first_low, ctx["cur"]) if d > 0 else max(first_low, ctx["cur"])
    if d * (edge - inv) <= 0.2 * atr:  # 이미 깨졌거나 너무 가까우면 눌림 지점 너머로
        inv = edge - d * 0.5 * atr
        inv_note = "첫 눌림 지점보다 더 밀리면 무효" if d > 0 else "첫 반등 지점보다 더 오르면 무효"
    elif d * (edge - inv) > 1.2 * amp_d:  # 직전 스윙이 너무 멀면: 눌림 너머 첫 가격대
        near = sorted([lv for lv in ctx["levels"] if d * (edge - lv["log"]) > 0.5 * atr],
                      key=lambda x: d * (edge - x["log"]))
        inv = (near[0]["log"] if near else edge - d * 0.5 * amp_d) - d * 0.3 * atr
        inv_note = f"가까운 {'지지' if d > 0 else '저항'}({_fmt(math.exp(inv))}) {'이탈' if d > 0 else '돌파'} — 되돌림이 예상보다 깊음"
    else:
        inv_note = "직전 스윙 저점 이탈(다우 이론: 저점이 낮아짐)" if d > 0 else "직전 스윙 고점 돌파(다우 이론: 고점이 높아짐)"
    return {"direction": "up" if d > 0 else "down", "pts": b.pts, "first_target": first_target,
            "invalidation": (inv, inv_note)}


def build_range(ctx: dict) -> dict:
    """박스권 시나리오: 가까운 지지·저항 사이 왕복."""
    st, atr, cur = ctx["stats"], ctx["atr_rel"], ctx["cur"]
    amp = (st["amp_up"] + st["amp_dn"]) / 2
    sup = [lv for lv in ctx["levels"] if 0.5 * atr < cur - lv["log"] <= 1.2 * amp]
    res = [lv for lv in ctx["levels"] if 0.5 * atr < lv["log"] - cur <= 1.2 * amp]
    s = max(sup, key=lambda x: x["strength"]) if sup else {"log": cur - 0.5 * amp, "note": "평균 파동 절반 아래"}
    r = max(res, key=lambda x: x["strength"]) if res else {"log": cur + 0.5 * amp, "note": "평균 파동 절반 위"}
    b = _Builder(ctx, 0)
    go_up = ctx["cur_dir"] >= 0
    i = 0
    while not b.done():
        top = (i == 0 and go_up) or (i > 0 and b.pos < (s["log"] + r["log"]) / 2)
        tgt = r if top else s
        # 박스 안쪽에서 조금씩 못 미치거나 살짝 넘는 정도로(가짜 돌파 포함) 변화를 준다
        jitter = (0.15 if i % 3 == 2 else -0.1) * atr * (1 if top else -1)
        b.leg(tgt["log"] + jitter, f"박스 {'상단' if top else '하단'}: {tgt['note']}", "range")
        i += 1
    return {"direction": "range", "pts": b.pts, "box": (s, r), "first_target": r if go_up else s,
            "invalidation": None}


# ───────────────────────── 가상 캔들 ─────────────────────────
def synth_candles(pts: list, H: int, sigma: float, wick: float, cur: float, seed: int) -> dict:
    """경유점을 잇는 캔들. 파동 위에 AR(1) 잔물결(봉마다 sigma 정도 흔들림)을 얹고 끝점은 경유점에 맞춘다."""
    rng = np.random.default_rng(seed)
    close = np.empty(pts[-1][0] + 1)
    close[0] = cur
    for (b0, p0, *_), (b1, p1, *_) in zip(pts[:-1], pts[1:]):
        n = b1 - b0
        k = np.arange(1, n + 1)
        # 파동 안 속도 변화: 시작은 빠르게, 끝은 느리게(가벼운 S자)
        u = k / n
        base = p0 + (p1 - p0) * (u + 0.12 * np.sin(2 * np.pi * u))
        x = np.zeros(n)
        e = rng.normal(0, sigma, n)
        for j in range(n):
            x[j] = (0.75 * x[j - 1] if j else 0) + e[j]
        x -= u * x[-1]
        seg = base + x
        lo_b, hi_b = min(p0, p1) - 0.6 * sigma, max(p0, p1) + 0.6 * sigma
        seg = np.clip(seg, lo_b, hi_b)
        seg[-1] = p1
        close[b0 + 1:b1 + 1] = seg
    close = close[1:H + 1]
    open_ = np.r_[cur, close[:-1]]
    w_up = np.abs(rng.normal(0, wick, len(close)))
    w_dn = np.abs(rng.normal(0, wick, len(close)))
    high = np.maximum(open_, close) + w_up
    low = np.minimum(open_, close) - w_dn
    f = lambda a: np.exp(a)  # noqa: E731
    return {"o": f(open_), "h": f(high), "l": f(low), "c": f(close)}


def future_times(last: pd.Timestamp, tf: str, n: int) -> list[int]:
    if tf == "1M":
        return [int((last + pd.DateOffset(months=i + 1)).timestamp()) for i in range(n)]
    base = int(last.timestamp())
    return [base + STEP_SEC[tf] * (i + 1) for i in range(n)]


# ───────────────────────── 조립 ─────────────────────────
def context(df: pd.DataFrame, ind: pd.DataFrame, tf: str) -> dict | None:
    cfg = TF_CFG[tf]
    look = cfg["look"]
    d = df.iloc[-look:] if look else df
    a = ind["atr14"].reindex(d.index).to_numpy()
    c = d["close"].to_numpy()
    atr_rel_arr = np.log1p(np.nan_to_num(a / c, nan=np.nanmedian(a / c)))
    thr = cfg["zz"] * atr_rel_arr
    piv, cur_dir, ext = zigzag(d["high"].to_numpy(), d["low"].to_numpy(), thr)
    if len(piv) < 3:
        return None
    lr = np.diff(np.log(c))
    sigma = float(np.median(np.abs(lr[-120:])) * 1.25)
    cur = float(np.log(c[-1]))
    atr_rel = float(atr_rel_arr[-1])
    stats = swing_stats(piv, sigma)
    H = cfg["horizon"]
    ext_log = float(np.log(d["high"].iloc[ext] if cur_dir == 1 else d["low"].iloc[ext]))
    levels = find_levels(piv, atr_rel, cur)
    # 이동평균도 동적 지지/저항으로
    for k, nm in (("sma50", "50선"), ("sma200", "200선")):
        v = float(ind[k].iloc[-1])
        if not math.isnan(v):
            levels.append({"log": math.log(v), "touches": 0, "strength": 0.5, "src": "ma",
                           "note": f"{nm}({'저항' if math.log(v) > cur else '지지'})"})
    # 목표 범위: 기간 동안 변동성으로 갈 수 있는 거리(약 2.2σ√H) 안의 가격만
    maxdist = 2.2 * sigma * math.sqrt(H) + 0.5 * (stats["amp_up"] + stats["amp_dn"]) / 2
    wick = float(np.median(np.log(d["high"] / d[["open", "close"]].max(axis=1)).iloc[-120:]) +
                 np.median(np.log(d[["open", "close"]].min(axis=1) / d["low"]).iloc[-120:])) / 2 * 1.25
    return {"tf": tf, "piv": piv, "cur_dir": cur_dir, "ext_log": ext_log, "cur": cur, "atr_rel": atr_rel,
            "sigma": sigma, "stats": stats, "H": H, "levels": levels, "maxdist": maxdist, "wick": wick,
            "index": d.index}


def plan(df: pd.DataFrame, ind: pd.DataFrame, tf: str) -> dict | None:
    """주·대안 시나리오의 뼈대(경유점·목표·무효화). 캔들 없이 — 백테스트에서도 사용."""
    ctx = context(df, ind, tf)
    if ctx is None:
        return None
    struct = structure(ctx["piv"])
    ev = evidence(df, ind, struct)
    sc = ev["score"]
    if sc >= 0.25 or sc <= -0.25:
        d = 1 if sc > 0 else -1
        primary = build_trend(ctx, d)
        # 대안: 반대 방향 전환 — 무효화 가격(직전 스윙 저점/고점) 이탈이 첫 관문
        inv = primary["invalidation"]
        ctx_alt = {**ctx, "break_level": (inv[0], "직전 스윙 " + ("저점 이탈" if d > 0 else "고점 돌파"))}
        alt = build_trend(ctx_alt, -d, label_first=("고점 재시험 실패" if d > 0 else "저점 재시험 후 반등") if ctx["cur_dir"] == d else None)
        primary["kind"], alt["kind"] = "trend", "reversal"
    else:
        primary = build_range(ctx)
        primary["kind"] = "range"
        d = 1 if sc > 0 else -1 if sc < 0 else (ctx["cur_dir"] or 1)
        s, r = primary["box"]
        brk = r if d > 0 else s
        hold = s if d > 0 else r
        ctx_alt = {**ctx, "break_level": (brk["log"], f"박스 {'상단 돌파' if d > 0 else '하단 이탈'}"),
                   "pullback_override": (hold["log"], f"박스 {'하단' if d > 0 else '상단'} 재확인")}
        alt = build_trend(ctx_alt, d)
        alt["kind"] = "breakout"
    return {"ctx": ctx, "struct": struct, "evidence": ev, "primary": primary, "alternate": alt}


def _fmt(p: float) -> str:
    return f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}"


def _title(s: dict) -> str:
    k, dr = s["kind"], s["direction"]
    pts = s["pts"]
    pb = len(pts) > 1 and pts[1][3] == "pullback"
    if k == "trend":
        return f"{'눌림 후 ' if pb else ''}{TOPIC_KO[dr]} 추세 지속"
    if k == "reversal":
        return f"{'반등 실패 후 ' if dr == 'down' and pb else '반락 후 ' if pb else ''}{TOPIC_KO[dr]} 전환"
    if k == "breakout":
        return f"박스 {'상단' if dr == 'up' else '하단'} {'돌파' if dr == 'up' else '이탈'} 후 {TOPIC_KO[dr]}"
    return "지지·저항 사이 박스권"


def _export(s: dict, ctx: dict, times: list[int], seed: int, role: str) -> dict:
    H = ctx["H"]
    cd = synth_candles(s["pts"], H, ctx["sigma"], ctx["wick"], ctx["cur"], seed)
    r2 = lambda a: [round(float(x), 2) for x in a]  # noqa: E731
    steps = []
    for b, lp, note, kind in s["pts"][1:]:
        if b > H:
            break
        steps.append({"t": times[b - 1], "bars": int(b), "price": round(math.exp(lp), 2), "kind": kind, "note_ko": note})
    cur_p = math.exp(ctx["cur"])
    ft = math.exp(s["first_target"]["log"])
    inv = s.get("invalidation")
    inv_p = round(math.exp(inv[0]), 2) if inv else None
    # 기간 안 가장 멀리 간 목표(경유점 중 극값)
    if s["direction"] == "range":
        lo, hi = (math.exp(x["log"]) for x in s["box"])
        txt = (f"{_fmt(lo)}(지지) ~ {_fmt(hi)}(저항) 사이를 오가며 방향을 정하지 못하는 흐름. "
               f"두 가격대 중 하나를 종가로 뚜렷하게 벗어나면 이 시나리오는 끝.")
        far = None
    else:
        sgn = 1 if s["direction"] == "up" else -1
        far_lp = max((p[1] for p in s["pts"] if p[0] <= H), key=lambda v: sgn * v)
        far = round(math.exp(far_lp), 2)
        parts = []
        for i, st in enumerate(steps[:4]):
            parts.append(f"{'①②③④'[i]} {_fmt(st['price'])} {st['note_ko']}")
        txt = " → ".join(parts)
        if inv_p:
            txt += f". 무효화: {_fmt(inv_p)} {'아래' if sgn > 0 else '위'} 마감({inv[1]})"
    return {
        "role": role,
        "kind": s["kind"],
        "direction": s["direction"],
        "label_ko": _title(s),
        "text_ko": txt,
        "first_target": {"price": round(ft, 2), "change": round(ft / cur_p - 1, 4), "note_ko": s["first_target"]["note"]},
        "furthest": {"price": far, "change": round(far / cur_p - 1, 4)} if far else None,
        "invalidation": {"price": inv_p, "change": round(inv_p / cur_p - 1, 4), "note_ko": inv[1]} if inv_p else None,
        "box": [round(math.exp(x["log"]), 2) for x in s["box"]] if s["direction"] == "range" else None,
        "steps": steps,
        "candles": {"t": times[:H], "o": r2(cd["o"]), "h": r2(cd["h"]), "l": r2(cd["l"]), "c": r2(cd["c"])},
    }


def analyze(df: pd.DataFrame, ind: pd.DataFrame, tf: str, seed: int = 7) -> dict | None:
    pl = plan(df, ind, tf)
    if pl is None:
        return None
    ctx = pl["ctx"]
    times = future_times(df.index[-1], tf, ctx["H"])
    ev = pl["evidence"]
    prim = _export(pl["primary"], ctx, times, seed, "primary")
    alt = _export(pl["alternate"], ctx, times, seed + 1, "alternate")
    # 근거 비중: 주 시나리오 쪽 근거 수 / 방향이 있는 근거 수 (확률이 아님)
    if prim["direction"] == "range":
        share = round(float(np.clip(0.5 + (0.25 - abs(ev["score"])), 0.5, 0.75)), 2)
    else:
        n = ev["bull"] + ev["bear"]
        share = round((ev["bull"] if prim["direction"] == "up" else ev["bear"]) / n, 2) if n else 0.5
    prim["evidence_share"], alt["evidence_share"] = share, round(1 - share, 2)
    st = ctx["stats"]
    piv = ctx["piv"][-6:]
    return {
        "method_ko": ("다우 이론 고점·저점 구조, 지그재그 스윙, 지지·저항(역할 전환), 피보나치 되돌림·확장, "
                      "측정 이동, 이동평균·MACD·RSI·볼린저·거래량 근거 점수"),
        "interval": tf,
        "structure": {"code": pl["struct"]["code"], "label_ko": pl["struct"]["label_ko"],
                      "pivots": [{"t": int(ctx["index"][p[0]].timestamp()), "price": round(math.exp(p[1]), 2),
                                  "type": "high" if p[2] == 1 else "low"} for p in piv]},
        "evidence": ev,
        "swing": {"median_leg_up_pct": round(math.exp(st["amp_up"]) - 1, 4),
                  "median_leg_down_pct": round(1 - math.exp(-st["amp_dn"]), 4),
                  "median_leg_bars": st["bars_med"],
                  "zigzag_atr": TF_CFG[tf]["zz"], "n_legs": st["n_legs"]},
        "scenarios": [prim, alt],
    }


# ───────────────────────── 백테스트 ─────────────────────────
def backtest(df: pd.DataFrame, ind: pd.DataFrame, tf: str) -> dict | None:
    """과거 각 시점에서 그때까지의 봉만으로 주 시나리오를 만들고, 이후 bt_h봉 동안
    '첫 목표'와 '무효화 가격' 중 무엇에 먼저 닿았는지 센다(추세형 주 시나리오만).
    기준선: 방향 없는 무작위 움직임이라면 목표가 먼저일 확률 ≈ 무효화까지 거리 / (두 거리 합)."""
    cfg = TF_CFG[tf]
    if not cfg["bt_h"]:
        return None
    H, step = cfg["bt_h"], cfg["bt_step"]
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    start = cfg["bt_from"]
    win = cfg["look"] or n
    tgt_first = inv_first = neither = 0
    base = []
    box_kept = box_n = 0
    for t in range(start, n - H, step):
        lo_i = max(0, t + 1 - win)
        pl = plan(df.iloc[lo_i:t + 1], ind.iloc[lo_i:t + 1], tf)
        if pl is None:
            continue
        p = pl["primary"]
        cur = pl["ctx"]["cur"]
        fh, fl = np.log(hi[t + 1:t + 1 + H]), np.log(lo[t + 1:t + 1 + H])
        if p["kind"] == "range":
            s, r = p["box"]
            atr = pl["ctx"]["atr_rel"]
            box_n += 1
            box_kept += int(fh.max() <= r["log"] + atr and fl.min() >= s["log"] - atr)
            continue
        d = 1 if p["direction"] == "up" else -1
        tg, iv = p["first_target"]["log"], p["invalidation"][0]
        hit_t = np.argmax((fh >= tg) if d > 0 else (fl <= tg)) if ((fh >= tg).any() if d > 0 else (fl <= tg).any()) else None
        hit_i = np.argmax((fl <= iv) if d > 0 else (fh >= iv)) if ((fl <= iv).any() if d > 0 else (fh >= iv).any()) else None
        if hit_t is None and hit_i is None:
            neither += 1
        elif hit_i is None or (hit_t is not None and hit_t < hit_i):
            tgt_first += 1
        else:
            inv_first += 1
        dt, di = abs(tg - cur), abs(cur - iv)
        base.append(di / (dt + di) if dt + di > 0 else 0.5)
    m = tgt_first + inv_first + neither
    if m < 20:
        return None
    resolved = tgt_first + inv_first
    return {
        "n": m, "horizon_bars": H, "step_bars": step,
        "period": [df.index[start].strftime("%Y-%m-%d"), df.index[n - H - 1].strftime("%Y-%m-%d")],
        "target_first": round(tgt_first / m, 3), "invalidation_first": round(inv_first / m, 3),
        "neither": round(neither / m, 3),
        "target_first_resolved": round(tgt_first / resolved, 3) if resolved else None,
        "baseline_resolved": round(float(np.mean(base)), 3) if base else None,
        "range_n": box_n, "range_kept": round(box_kept / box_n, 3) if box_n >= 10 else None,
    }


# ───────────────────────── 통계 모델과 교차 확인 ─────────────────────────
def stat_check(cum: np.ndarray, hi: np.ndarray, lo: np.ndarray, price: float, sc: dict, days: int) -> dict:
    """통계 모델 경로(현재가 대비 로그수익률, 일 단위)로 본 이 시나리오의 첫 목표·무효화 도달 확률.

    target_first: 기간 안에 첫 목표가 무효화 가격보다 먼저 닿은 경로 비율(같은 날이면 무효화 우선).
    """
    days = min(days, cum.shape[1])
    hi = np.maximum(hi[:, :days], cum[:, :days])
    lo = np.minimum(lo[:, :days], cum[:, :days])
    out = {"days": int(days)}
    tg = math.log(sc["first_target"]["price"] / price)
    hit_t = (hi >= tg) if tg > 0 else (lo <= tg)
    out["target_touch"] = round(float(hit_t.any(axis=1).mean()), 3)
    if sc.get("invalidation"):
        iv = math.log(sc["invalidation"]["price"] / price)
        hit_i = (hi >= iv) if iv > 0 else (lo <= iv)
        out["invalidation_touch"] = round(float(hit_i.any(axis=1).mean()), 3)
        big = days + 1
        ft = np.where(hit_t.any(axis=1), hit_t.argmax(axis=1), big)
        fi = np.where(hit_i.any(axis=1), hit_i.argmax(axis=1), big)
        out["target_first"] = round(float(((ft < fi) & (ft < big)).mean()), 3)
    if sc.get("box"):
        s_, r_ = (math.log(x / price) for x in sc["box"])
        out["box_kept"] = round(float(((hi.max(axis=1) <= r_) & (lo.min(axis=1) >= s_)).mean()), 3)
    return out
