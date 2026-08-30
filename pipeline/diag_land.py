# -*- coding: utf-8 -*-
"""이봉성 진단 — 강제 착륙 구간의 고도·상승률·모드를 기록한다.
창이 48.35초로 끝나는 실행과 57.5초로 끝나는 실행의 하강 곡선을 비교하기 위한 것.
usage: diag_land.py <rep>
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runtime import Runner
from pymavlink import mavutil
mav = mavutil.mavlink

REP = sys.argv[1]

class DiagRunner(Runner):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.trk = []          # (sim_ms, alt, climb, mode)
    def _handle(self, msg):
        super()._handle(msg)
        if msg.get_type() == 'GLOBAL_POSITION_INT':
            self.trk.append((msg.time_boot_ms, msg.relative_alt/1000.0,
                             -msg.vz/100.0, self.S.get('mode')))

R = DiagRunner(f"D-{REP}", expected_outcome=None, branch="variance")
R.connect(); R.preflight(); R.takeoff(40.0)
R.setp("SIM_GPS1_JAM", 1)
R.wait("fsLand", timeout=90)
R.wait_end()
R.report()

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", f"D-{REP}.json")
j = json.load(open(p, encoding="utf-8"))
j["track"] = [[t, round(a,2), round(c,2), m] for t,a,c,m in R.trk]
json.dump(j, open(p,"w"), ensure_ascii=False, indent=1)
print(f"    궤적 {len(R.trk)}점 기록")
