# -*- coding: utf-8 -*-
"""이동 실험 궤적 그림 — 참값 기준 수평 궤적과 고도."""
import json, os, math
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
HERE = os.path.dirname(os.path.abspath(__file__))
f = "/mnt/c/Windows/Fonts/malgun.ttf"
if os.path.exists(f):
    font_manager.fontManager.addfont(f)
    matplotlib.rc('font', family='Malgun Gothic')
    matplotlib.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
COL = {"DRIFT": ("#888", "대조군 — 지령 없음"), "PUSH": ("#c00", "전진 지령 (기수 -15도)")}
for cond in ("DRIFT", "PUSH"):
    p = os.path.join(HERE, "runs", f"MOVE-{cond}.json")
    if not os.path.exists(p): continue
    j = json.load(open(p, encoding="utf-8"))
    tr = j.get("truth_track") or []
    me = j.get("move_experiment", {})
    if not tr: continue
    t_land = (j.get("t_land_ms") or 0)/1000.0
    tr = [x for x in tr if x[0] >= t_land]
    if not tr: continue
    lat0, lon0 = tr[0][1], tr[0][2]
    mlat = 111320.0; mlon = 111320.0*math.cos(math.radians(lat0))
    xs = [(x[2]-lon0)*mlon for x in tr]
    ys = [(x[1]-lat0)*mlat for x in tr]
    ts = [x[0]-t_land for x in tr]
    alts = [x[3] for x in tr]
    c, lab = COL[cond]
    ax[0].plot(xs, ys, lw=1.8, color=c, label=f"{lab}  {me.get('displacement_m')} m")
    ax[0].plot(xs[-1], ys[-1], "o", color=c, ms=7)
    ax[1].plot(ts, alts, lw=1.6, color=c, label=lab)

ax[0].plot(0, 0, "k+", ms=12, mew=2)
ax[0].annotate("교란 시점", (0, 0), textcoords="offset points", xytext=(8, -14), fontsize=9)
ax[0].set_xlabel("동쪽 (m)"); ax[0].set_ylabel("북쪽 (m)")
ax[0].set_title("항법 상실 구간의 수평 궤적 (SITL 참값)")
ax[0].grid(alpha=.3); ax[0].legend(fontsize=8.5); ax[0].set_aspect("equal", adjustable="datalim")
ax[1].set_xlabel("LAND 진입 기준 경과 시간 (s)"); ax[1].set_ylabel("상대 고도 (m)")
ax[1].set_title("고도 유지"); ax[1].grid(alpha=.3); ax[1].legend(fontsize=8.5)

fig.tight_layout()
out = os.path.join(HERE, "figs", "MOVE.png"); os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out, dpi=160)
# 그림 사본을 둘 위치. 환경변수로 지정하지 않으면 저장소 안 figs/ 에 남긴다.
win = os.environ.get("UAV_FIG_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs"))
try:
    os.makedirs(win, exist_ok=True); fig.savefig(os.path.join(win, "MOVE_궤적.png"), dpi=160)
    print("[+] 바탕화면/드론실험결과/MOVE_궤적.png")
except Exception: print("[+]", out)
