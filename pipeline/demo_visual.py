# -*- coding: utf-8 -*-
"""직접 돌려보는 시각 실험 — 텔레메트리를 시계열로 기록하고 그림을 만든다.

사용법
  1) 터미널 A:  ~/ardupilot/build/sitl/bin/arducopter -S -I0 --model + --speedup 1 \
                  --defaults ~/ardupilot/Tools/autotest/default_params/copter.parm \
                  --home 34.7604,127.6622,0,0
  2) 터미널 B:  python3 demo_visual.py <명령이름>
       명령이름 = BASELINE | STABILIZE | ALT_HOLD | GUIDED_NOGPS | LOITER | RTL |
                  FLIGHTTERMINATION | DISARM
  3) 결과: figs/<이름>.png  (고도·모드·GPS 시계열에 사건 표시)

Mission Planner / QGroundControl 로 같은 SITL 에 붙으면 지도에서 실시간으로 볼 수 있다.
접속 주소는 TCP 127.0.0.1:5760 (WSL mirrored 모드 기준).
"""
import sys, os, time, json
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.path.join(_AP, "modules", "mavlink"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil
from runtime import Runner, RESULT
mav = mavutil.mavlink

HERE = os.path.dirname(os.path.abspath(__file__))
MODES = {"STABILIZE": 0, "ALT_HOLD": 2, "AUTO": 3, "GUIDED": 4, "LOITER": 5,
         "RTL": 6, "POSHOLD": 16, "BRAKE": 17, "GUIDED_NOGPS": 20, "SMART_RTL": 21}
TERMINAL = {"FLIGHTTERMINATION": mav.MAV_CMD_DO_FLIGHTTERMINATION,
            "DISARM": mav.MAV_CMD_COMPONENT_ARM_DISARM}


class VisualRunner(Runner):
    """Runner 에 시계열 기록만 추가한다. 판정 논리는 건드리지 않는다."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.series = []            # (sim_s, alt, mode, fix, armed)

    def _handle(self, msg):
        super()._handle(msg)
        if msg.get_type() == 'GLOBAL_POSITION_INT':
            self.series.append((self.S['simms'] / 1000.0, self.S['alt'],
                                self.S['mode'], self.S['fix'], int(self.S['armed'])))

    def report(self):
        super().report()
        p = os.path.join(HERE, "runs", f"{self.sid}.json")
        j = json.load(open(p, encoding="utf-8"))
        j["series"] = self.series
        json.dump(j, open(p, "w"), ensure_ascii=False, indent=1)
        plot(self.sid)


def plot(sid):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for cand in ("/mnt/c/Windows/Fonts/malgun.ttf",):
        if os.path.exists(cand):
            font_manager.fontManager.addfont(cand)
            matplotlib.rc('font', family='Malgun Gothic')
            matplotlib.rcParams['axes.unicode_minus'] = False
            break

    j = json.load(open(os.path.join(HERE, "runs", f"{sid}.json"), encoding="utf-8"))
    s = j.get("series") or []
    if not s:
        print("[!] 시계열 없음"); return
    t0 = j["t_land_ms"] / 1000.0 if j.get("t_land_ms") else s[0][0]
    ts = [x[0] - t0 for x in s]
    alt = [x[1] for x in s]
    fix = [x[3] for x in s]

    fig, ax = plt.subplots(2, 1, figsize=(9, 5.4), sharex=True,
                           gridspec_kw=dict(height_ratios=[3, 1]))
    ax[0].plot(ts, alt, lw=1.6, color="#222")
    ax[0].set_ylabel("상대 고도 (m)")
    ax[0].set_title(f"{sid} — {j.get('branch')} 분기 | 창 {j.get('window_s')} s | "
                    f"판정 {j.get('outcome_reclassified') or j.get('outcome')}")
    ax[0].grid(alpha=.3)
    ax[0].axvspan(0, (j["window_s"] or 0), color="#cfcfcf", alpha=.45,
                  label="injectWindow")

    styles = {"gnssLost": ("#777", ":"), "navBranch": ("#777", "-."),
              "fsLand": ("#000", "-"), "cmdAccepted": ("#c00", "-"),
              "motorsDisarmed": ("#06c", "--"), "landed": ("#080", "--")}
    for pred, ms in j["chain"]:
        if pred not in styles: continue
        c, ls = styles[pred]
        x = ms / 1000.0 - t0
        ax[0].axvline(x, color=c, ls=ls, lw=1.3)
        ax[0].annotate(pred, (x, max(alt) * 0.96), rotation=90, fontsize=7.5,
                       color=c, ha="right", va="top")
    ax[0].legend(loc="upper right", fontsize=8)

    ax[1].step(ts, fix, where="post", color="#444", lw=1.3)
    ax[1].set_ylabel("GPS fix"); ax[1].set_xlabel("LAND 진입 기준 경과 시간 (s)")
    ax[1].set_yticks([0, 1, 2, 3]); ax[1].grid(alpha=.3)

    os.makedirs(os.path.join(HERE, "figs"), exist_ok=True)
    out = os.path.join(HERE, "figs", f"{sid}.png")
    fig.tight_layout(); fig.savefig(out, dpi=160)
    # 바탕화면에도 같이 저장한다 (WSL /tmp 안은 탐색기에서 찾기 어렵다)
    # 그림 사본을 둘 위치. 환경변수로 지정하지 않으면 저장소 안 figs/ 에 남긴다.
    win = os.environ.get("UAV_FIG_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs"))
    try:
        os.makedirs(win, exist_ok=True)
        fig.savefig(os.path.join(win, f"{sid}.png"), dpi=160)
        print(f"[+] 그림 저장: 바탕화면/드론실험결과/{sid}.png")
    except Exception:
        print(f"[+] 그림 저장: {out}")
    plt.close(fig)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "BASELINE"
    R = VisualRunner(f"V-{name}", expected_outcome=None, branch="variance")
    R.connect(); R.preflight(); R.takeoff(40.0)
    R.setp("SIM_GPS1_JAM", 1)
    R.wait("fsLand", timeout=90)
    if name != "BASELINE":
        if name in MODES:      R.send_mode(name, MODES[name])
        elif name in TERMINAL: R.send_cmd(TERMINAL[name])
        else: raise SystemExit(f"알 수 없는 명령: {name}")
    R.wait_end()
    R.report()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plot-only":
        plot(sys.argv[2])
    else:
        main()
