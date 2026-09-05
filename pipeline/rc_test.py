# -*- coding: utf-8 -*-
"""RC 스로틀을 통제한 조건에서 제어효과 창을 다시 잰다.

4.2 의 ALT_HOLD 접지 속도 2.509 m/s 는 조종사 입력의 최대 수직 속도
기본값 2.5 m/s 와 가깝다. 주 실험은 RC 를 통제하지 않았으므로 관측된
창 단축이 RC 입력에 얼마나 의존하는지 알 수 없다. 스로틀을 최하단과
중립으로 고정하고 무주입·ALT_HOLD 를 각각 재어 그 의존성을 본다.

usage: rc_test.py {LOW|MID} {BASELINE|ALT_HOLD|STABILIZE} <rep>
"""
import sys, os, time
sys.path.insert(0, os.environ.get("PYMAVLINK_PATH", ""))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil
from runtime import Runner

mav = mavutil.mavlink
THR = {"LOW": 1000, "MID": 1500}          # 스로틀 PWM
MODE = {"ALT_HOLD": 2, "STABILIZE": 0}    # ArduCopter 모드 번호

thr_name = (sys.argv[1] if len(sys.argv) > 1 else "LOW").upper()
cond     = (sys.argv[2] if len(sys.argv) > 2 else "BASELINE").upper()
rep      = int(sys.argv[3]) if len(sys.argv) > 3 else 1
SID = f"RC-{thr_name}-{cond}-{rep:02d}"
assert thr_name in THR and (cond == "BASELINE" or cond in MODE)


def main():
    g = Runner(SID, expected_outcome=None, branch="variance")
    g.connect()

    def hold_rc(dur):
        """RC override 는 유지 시간이 짧아 되풀이해 보내야 한다."""
        t0 = time.time()
        while time.time() - t0 < dur:
            g.m.mav.rc_channels_override_send(
                g.m.target_system, g.m.target_component,
                1500, 1500, THR[thr_name], 1500, 0, 0, 0, 0)
            g.pump(0.25)

    g.preflight()
    ok = g.takeoff(40.0)
    print(f"[i] 이륙 후 고도 {g.S.get('alt')} · 스로틀 {thr_name}({THR[thr_name]})", flush=True)

    hold_rc(1.5)                       # 상승 완료 뒤부터 스로틀을 잡는다
    g.setp("SIM_GPS1_JAM", 1)
    got = g.wait("fsLand", timeout=90)
    hold_rc(0.5)

    if cond in MODE:
        g.send_mode(cond, MODE[cond])

    # 종료까지 스로틀을 유지한다. wait_end 는 자체 pump 를 돌리므로
    # 짧은 구간으로 나누어 override 를 끼워 넣는다.
    t0 = time.time()
    while time.time() - t0 < 200 and g.t_disarm is None and g.t_onground is None:
        hold_rc(1.0)

    g.extra = dict(rc_throttle_pwm=THR[thr_name], rc_profile=thr_name,
                   condition=cond, window_entered=got,
                   takeoff_alt_m=40.0, rc_override=True)
    print(f"\n[=] {SID} | 스로틀 {thr_name} | 조건 {cond} | 창진입 {got}", flush=True)
    g.report()


main()
