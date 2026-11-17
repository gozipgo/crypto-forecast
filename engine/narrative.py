"""지표별 현재 상태를 한국어 한두 줄로 요약."""
from __future__ import annotations

import math

import pandas as pd


def _f(x) -> float | None:
    x = float(x)
    return None if math.isnan(x) else x


def fmt_price(p: float) -> str:
    return f"${p:,.0f}" if p >= 100 else f"${p:,.2f}"


def summarize(df: pd.DataFrame, ind: pd.DataFrame, tf_label: str) -> dict:
    """tf_label: '1시간봉' 등. 각 항목은 value/signal/text_ko."""
    c = float(df["close"].iloc[-1])
    L, P = ind.iloc[-1], ind.iloc[-2]
    out: dict = {}

    # 이동평균
    mas = {n: _f(L[f"sma{n}"]) for n in (20, 50, 200)}
    avail = {n: v for n, v in mas.items() if v is not None}
    above = [n for n, v in avail.items() if c > v]
    if len(avail) == 3 and mas[20] > mas[50] > mas[200]:
        arr, sig = "정배열(20>50>200)", "bullish"
    elif len(avail) == 3 and mas[20] < mas[50] < mas[200]:
        arr, sig = "역배열(20<50<200)", "bearish"
    elif len(avail) == 2 and mas[20] > mas[50]:
        arr, sig = "단기 정배열(20>50, 200은 데이터 부족)", "bullish"
    elif len(avail) == 2 and mas[20] < mas[50]:
        arr, sig = "단기 역배열(20<50, 200은 데이터 부족)", "bearish"
    else:
        arr, sig = "혼조 배열", "neutral"
    cross = ""
    if mas[50] and mas[200] and _f(P["sma50"]) and _f(P["sma200"]):
        if P["sma50"] <= P["sma200"] and L["sma50"] > L["sma200"]:
            cross, sig = " 방금 골든크로스 발생.", "bullish"
        elif P["sma50"] >= P["sma200"] and L["sma50"] < L["sma200"]:
            cross, sig = " 방금 데드크로스 발생.", "bearish"
    out["ma"] = {
        "values": {f"sma{n}": (round(v, 2) if v else None) for n, v in mas.items()},
        "signal": sig,
        "text_ko": f"{tf_label} 이동평균은 {arr}. 가격은 {len(above)}/{len(avail)}개 평균선 위에 있음.{cross}",
    }

    # RSI
    r = _f(L["rsi14"])
    if r is None:
        rs, rt = "neutral", "데이터 부족"
    elif r >= 70:
        rs, rt = "overbought", f"RSI {r:.0f}, 과매수 구간 — 단기 과열, 되돌림 가능성 주의"
    elif r >= 55:
        rs, rt = "bullish", f"RSI {r:.0f}, 매수세 우위"
    elif r > 45:
        rs, rt = "neutral", f"RSI {r:.0f}, 중립"
    elif r > 30:
        rs, rt = "bearish", f"RSI {r:.0f}, 매도세 우위" + (" — 과매도 근처" if r < 35 else "")
    else:
        rs, rt = "oversold", f"RSI {r:.0f}, 과매도 구간 — 단기 반등 여지, 다만 하락 추세에선 오래 머물 수 있음"
    out["rsi14"] = {"value": round(r, 1) if r is not None else None, "signal": rs, "text_ko": rt}

    # MACD
    h, hp = _f(L["hist"]), _f(P["hist"])
    m = _f(L["macd"])
    if h is None:
        ms, mt = "neutral", "데이터 부족"
    else:
        if hp is not None and hp <= 0 < h:
            ms, mt = "bullish", "MACD가 시그널선을 상향 돌파 — 상승 전환 신호"
        elif hp is not None and hp >= 0 > h:
            ms, mt = "bearish", "MACD가 시그널선을 하향 돌파 — 하락 전환 신호"
        elif h > 0:
            ms = "bullish"
            mt = "MACD가 시그널선 위, 상승 모멘텀 " + ("강해지는 중" if hp is not None and h > hp else "약해지는 중")
        else:
            ms = "bearish"
            mt = "MACD가 시그널선 아래, 하락 모멘텀 " + ("강해지는 중" if hp is not None and h < hp else "약해지는 중")
        mt += f" (0선 {'위' if m > 0 else '아래'})"
    out["macd"] = {"value": round(m, 2) if m is not None else None,
                   "signal_line": round(_f(L["signal"]) or 0, 2), "hist": round(h, 2) if h is not None else None,
                   "signal": ms, "text_ko": mt}

    # 볼린저
    pb, w = _f(L["bb_pctb"]), _f(L["bb_width"])
    wq = float((ind["bb_width"].dropna().iloc[-120:] < w).mean()) if w is not None else None
    if pb is None:
        bs, bt = "neutral", "데이터 부족"
    else:
        if pb > 1:
            bs, bt = "overbought", "가격이 상단 밴드를 넘어섬 — 강한 상승이지만 과열"
        elif pb > 0.8:
            bs, bt = "bullish", "상단 밴드 근처 — 상승 압력"
        elif pb < 0:
            bs, bt = "oversold", "가격이 하단 밴드 아래 — 강한 하락이지만 과매도"
        elif pb < 0.2:
            bs, bt = "bearish", "하단 밴드 근처 — 하락 압력"
        else:
            bs, bt = "neutral", "밴드 중간 — 방향성 약함"
        if wq is not None and wq < 0.15:
            bt += ". 밴드 폭이 최근 120봉 중 매우 좁음(스퀴즈) — 큰 변동이 다가올 수 있음"
    out["bollinger"] = {"pctb": round(pb, 3) if pb is not None else None,
                        "width": round(w, 4) if w is not None else None,
                        "upper": round(_f(L["bb_upper"]) or 0, 2), "lower": round(_f(L["bb_lower"]) or 0, 2),
                        "signal": bs, "text_ko": bt}

    # 거래량 (진행 중인 마지막 봉은 덜 쌓였으므로 직전 완성봉 기준)
    vr = _f(ind["vol_ratio"].iloc[-2])
    chg = float(df["close"].iloc[-2] / df["close"].iloc[-3] - 1)
    if vr is None:
        vs, vt = "neutral", "데이터 부족"
    elif vr >= 1.8:
        vs = "bullish" if chg > 0 else "bearish"
        vt = f"직전 봉 거래량이 평균의 {vr:.1f}배 — {'상승' if chg > 0 else '하락'}에 힘이 실림"
    elif vr >= 1.3:
        vs, vt = "neutral", f"직전 봉 거래량이 평균보다 많음({vr:.1f}배) — {'상승' if chg > 0 else '하락'} 쪽 관심 증가"
    elif vr <= 0.6:
        vs, vt = "neutral", f"거래량이 평균의 {vr:.1f}배로 한산 — 움직임의 신뢰도 낮음"
    else:
        vs, vt = "neutral", f"거래량은 평균 수준({vr:.1f}배)"
    out["volume"] = {"ratio": round(vr, 2) if vr is not None else None, "signal": vs, "text_ko": vt}
    return out
