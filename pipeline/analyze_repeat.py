# -*- coding: utf-8 -*-
"""반복 측정 분석 — 사전 등록(실험설계_반복측정.md)한 절차를 그대로 수행한다.

주 결과변수 : 제어효과 창 w (s)
H1 (차이)   : BASELINE 대 {ALT_HOLD, STABILIZE, DISARM}, Mann-Whitney U 양측 정확검정 + Holm 보정
H2 (동등)   : BASELINE 대 LOITER, 동등성 마진 ±2.0 s 의 TOST
제외 규칙   : failures 가 있거나 창이 정의되지 않은 비행은 제외하고 사유를 보고한다
"""
import json, glob, os, itertools, sys

# 사전 등록은 조건당 5회다. 인자로 상한을 주면 확장 측정까지 포함해 분석한다.
NMAX = int(sys.argv[1]) if len(sys.argv) > 1 else 5
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
COND = ["BASELINE", "LOITER", "ALT_HOLD", "STABILIZE", "DISARM"]
MARGIN = 2.0          # 사전 등록한 동등성 마진 (초)

# ── 수집 (사전 등록한 rep 1~5 만. rep 0 은 사전 점검용이라 제외)
data, excluded = {c: [] for c in COND}, []
for f in sorted(glob.glob(os.path.join(HERE, "runs", "R-*.json"))):
    j = json.load(open(f, encoding="utf-8"))
    name = j["id"].split("-")[1]; rep = int(j["id"].split("-")[2])
    if rep < 1 or rep > NMAX:
        # rep 0(사전 점검)과 지정 범위 밖(사후 검증 실행 등)은 넣지 않는다.
        excluded.append((j["id"], "분석 범위(rep 1~%d) 밖" % NMAX)); continue
    if j.get("failures"):
        excluded.append((j["id"], "; ".join(j["failures"]))); continue
    if j.get("window_s") is None:
        excluded.append((j["id"], "창 미정의 (관측 구간 내 미종료)")); continue
    data[name].append((rep, j["window_s"], j.get("impact_mps")))

def desc(v):
    if not v: return None
    q1, q2, q3 = stats.scoreatpercentile(v, [25, 50, 75])
    return dict(n=len(v), med=q2, q1=q1, q3=q3, lo=min(v), hi=max(v))

def cles(a, b):
    """공통언어 효과크기: 무작위로 뽑은 a 가 b 보다 클 확률."""
    w = sum((x > y) + 0.5*(x == y) for x in a for y in b)
    return w / (len(a)*len(b))

print("="*78)
print("반복 측정 분석 — 사전 등록 절차")
print("="*78)
if excluded:
    print("\n[제외된 비행]")
    for i, r in excluded: print("  %-18s %s" % (i, r))
else:
    print("\n[제외된 비행] 없음")

print("\n[기술통계] 제어효과 창 w (초)")
print("  %-11s %3s %8s %8s %8s %8s %8s" % ("조건","n","중앙값","Q1","Q3","최소","최대"))
W = {}
for c in COND:
    v = sorted(x[1] for x in data[c]); W[c] = v
    d = desc(v)
    if d: print("  %-11s %3d %8.2f %8.2f %8.2f %8.2f %8.2f" % (c, d["n"], d["med"], d["q1"], d["q3"], d["lo"], d["hi"]))
    else: print("  %-11s %3d  (유효 표본 없음)" % (c, 0))

print("\n[기술통계] 접지 속도 v (m/s) — 공중 종료는 결측")
for c in COND:
    v = sorted(x[2] for x in data[c] if x[2] is not None)
    if v: print("  %-11s n=%d  중앙값 %.3f  범위 %.3f~%.3f" % (c, len(v), stats.scoreatpercentile(v,50), min(v), max(v)))
    else: print("  %-11s 관측 없음 (전건 공중 종료)" % c)

# ── H1
print("\n[H1] 수락 명령의 창은 무주입 기준과 다른가 — Mann-Whitney U 양측 정확검정")
tests, raw = [], []
for c in ["ALT_HOLD", "STABILIZE", "DISARM"]:
    if len(W["BASELINE"]) < 3 or len(W[c]) < 3:
        print("  %-11s 유효 표본 부족 — 검정하지 않음" % c); continue
    u, p = stats.mannwhitneyu(W["BASELINE"], W[c], alternative="two-sided", method="exact")
    tests.append(c); raw.append(p)
    print("  %-11s U=%5.1f  p=%.4f  효과크기(CLES)=%.2f" % (c, u, p, cles(W["BASELINE"], W[c])))
if raw:
    order = sorted(range(len(raw)), key=lambda i: raw[i]); m = len(raw)
    holm, run = [0]*m, 0.0
    for k, i in enumerate(order):
        run = max(run, (m-k)*raw[i]); holm[i] = min(run, 1.0)
    print("  Holm 보정 p:", ", ".join("%s %.4f%s" % (tests[i], holm[i], " (유의)" if holm[i] < .05 else "") for i in range(m)))

# ── H2
print("\n[H2] 거부 명령의 창은 무주입 기준과 동등한가 — TOST, 마진 ±%.1f 초" % MARGIN)
a, b = W["BASELINE"], W["LOITER"]
if len(a) >= 3 and len(b) >= 3:
    d = stats.scoreatpercentile(a,50) - stats.scoreatpercentile(b,50)
    t1 = stats.ttest_ind(a, b, equal_var=False, alternative="greater")   # H0: 차이 <= -margin
    t2 = stats.ttest_ind(a, b, equal_var=False, alternative="less")      # H0: 차이 >= +margin
    import numpy as np
    lo = stats.ttest_ind(np.array(a)+MARGIN, b, equal_var=False, alternative="greater").pvalue
    hi = stats.ttest_ind(np.array(a)-MARGIN, b, equal_var=False, alternative="less").pvalue
    ptost = max(lo, hi)
    u, pmw = stats.mannwhitneyu(a, b, alternative="two-sided", method="exact")
    print("  중앙값 차이 %.2f 초" % d)
    print("  TOST  하한측 p=%.4f  상한측 p=%.4f  →  p=%.4f  %s" %
          (lo, hi, ptost, "동등성 성립" if ptost < .05 else "동등성 불성립 (표본 부족 또는 실제 차이)"))
    print("  참고: Mann-Whitney 양측 p=%.4f (유의하지 않음이 곧 같음은 아니다)" % pmw)
    print("  참고: CLES=%.2f" % cles(a, b))
else:
    print("  유효 표본 부족 — 검정하지 않음")

json.dump({c: [dict(rep=r, w=w, v=v) for r, w, v in sorted(data[c])] for c in COND},
          open(os.path.join(HERE, "repeat_result.json"), "w"), ensure_ascii=False, indent=1)
print("\n[+] repeat_result.json 기록")
