#!/usr/bin/env python3
"""고도 3수준(20/40/60 m) × 조건(BASELINE, ALT_HOLD) 제어효과 창 분석."""
import json, glob, os, statistics as st, itertools, math
P = os.path.dirname(os.path.abspath(__file__))

def load(pat, nmax=99):
    out = []
    for f in sorted(glob.glob(os.path.join(P, "runs", pat))):
        rep = int(f.rsplit("-", 1)[1].split(".")[0])
        if rep < 1 or rep > nmax: continue
        try: d = json.load(open(f))
        except Exception: continue   # 기록 중인 파일
        if d.get("window_s") is not None:
            out.append((rep, d["window_s"], d.get("impact_mps"), d.get("outcome")))
    return out

CELLS = [(20, "BASELINE", "V-ALT20-BASELINE-*.json"),
         (20, "ALT_HOLD", "V-ALT20-ALT_HOLD-*.json"),
         (40, "BASELINE", "R-BASELINE-*.json"),
         (40, "ALT_HOLD", "R-ALT_HOLD-*.json"),
         (60, "BASELINE", "V-ALT60-BASELINE-*.json"),
         (60, "ALT_HOLD", "V-ALT60-ALT_HOLD-*.json")]

def mw_exact(a, b):
    """Mann-Whitney U 양측 검정.

    작은 표본은 U 통계량의 정확 분포를 순열로 계산한다. 이전 판은 같은
    이름으로 중앙값 차이 순열검정을 수행하여 이름과 구현이 어긋나 있었다.
    """
    na, nb = len(a), len(b)

    def U_of(g1, g2):
        return sum((x > y) + 0.5 * (x == y) for x in g1 for y in g2)

    obs = U_of(a, b)
    if na + nb <= 20:                      # 정확검정
        allv = a + b
        cnt = tot = 0
        for comb in itertools.combinations(range(na + nb), na):
            g1 = [allv[k] for k in comb]
            g2 = [allv[k] for k in range(na + nb) if k not in comb]
            u = U_of(g1, g2); tot += 1
            if abs(u - na * nb / 2) >= abs(obs - na * nb / 2) - 1e-9: cnt += 1
        return cnt / tot, "정확검정"
    # 큰 표본은 동순위 보정을 넣은 정규근사
    allv = sorted(a + b)
    mu = na * nb / 2
    ties = 0
    for v in set(allv):
        t = allv.count(v)
        if t > 1: ties += t ** 3 - t
    N = na + nb
    sd = math.sqrt(na * nb / 12.0 * ((N + 1) - ties / (N * (N - 1.0))))
    z = (obs - mu) / sd
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))), "정규근사"


rows = []
print("=" * 74)
print("  제어효과 창의 고도 의존성 — ArduPilot SITL, commit c2b898a")
print("=" * 74)
print(f"{'고도':>5} {'조건':<10} {'n':>3} {'중앙값(s)':>10} {'최소':>8} {'최대':>8} {'IQR':>7}")
data = {}
for alt, cond, pat in CELLS:
    d = load(pat, 10 if alt != 40 else 30)
    w = sorted(x[1] for x in d)
    if not w: continue
    data[(alt, cond)] = w
    q = (st.quantiles(w, n=4)[2] - st.quantiles(w, n=4)[0]) if len(w) > 3 else 0.0
    print(f"{alt:>4}m {cond:<10} {len(w):>3} {st.median(w):>10.2f} {min(w):>8.2f} {max(w):>8.2f} {q:>7.2f}")
    rows.append((alt, cond, len(w), st.median(w), min(w), max(w)))

print("\n" + "-" * 74)
print("  조건 간 대비 (BASELINE 대 ALT_HOLD)")
print("-" * 74)
ps = []
for alt in (20, 40, 60):
    a, b = data.get((alt, "BASELINE")), data.get((alt, "ALT_HOLD"))
    if not a or not b: continue
    p, how = mw_exact(a, b)
    red = (st.median(a) - st.median(b)) / st.median(a) * 100
    ps.append((alt, p, how, red))
    print(f"  {alt:>2}m: 중앙값 {st.median(a):.2f} → {st.median(b):.2f} s "
          f"(단축 {red:.1f}%), p={p:.4g} [{how}]")

# Holm 보정
print("\n  Holm 보정 (3개 대비):")
srt = sorted(ps, key=lambda x: x[1])
m = len(srt)
prev = 0.0
for i, (alt, p, how, red) in enumerate(srt):
    adj = min(1.0, max(prev, p * (m - i))); prev = adj
    print(f"    {alt:>2}m: p={p:.4g} → p_adj={adj:.4g} {'유의' if adj < 0.05 else '비유의'}")

# 선형 적합 (최소제곱, 중앙값 기준)
print("\n" + "-" * 74)
print("  고도-창 선형 적합  w = a·h + b")
print("-" * 74)
for cond in ("BASELINE", "ALT_HOLD"):
    pts = [(alt, st.median(data[(alt, cond)])) for alt in (20, 40, 60) if (alt, cond) in data]
    if len(pts) < 3: continue
    n = len(pts); sx = sum(x for x, _ in pts); sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts); sxy = sum(x * y for x, y in pts)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx); b = (sy - a * sx) / n
    ybar = sy / n
    ss_t = sum((y - ybar) ** 2 for _, y in pts)
    ss_r = sum((y - (a * x + b)) ** 2 for x, y in pts)
    r2 = 1 - ss_r / ss_t if ss_t else float("nan")
    print(f"  {cond:<10} w = {a:.3f}·h + {b:.2f}   (R²={r2:.4f}, 1/a={1/a:.2f} m/s)")
    print(f"             예측 잔차: " + ", ".join(f"{alt}m {y-(a*alt+b):+.2f}s" for alt, y in pts))
