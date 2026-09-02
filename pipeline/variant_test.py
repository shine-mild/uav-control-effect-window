# -*- coding: utf-8 -*-
"""고도·기종 변형 측정. 창이 설정에 따라 어떻게 달라지는지 확인한다.

usage: variant_test.py <조건> <반복> <고도m> <태그>
  예) variant_test.py BASELINE 1 20 ALT20
      variant_test.py ALT_HOLD 1 40 HEXA
결과는 runs/V-{태그}-{조건}-{반복}.json 으로 남는다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runtime import Runner
from pymavlink import mavutil
mav = mavutil.mavlink

MODES    = {"STABILIZE": 0, "ALT_HOLD": 2, "LOITER": 5, "RTL": 6, "POSHOLD": 16,
            "AUTO": 3, "GUIDED": 4, "BRAKE": 17, "SMART_RTL": 21, "GUIDED_NOGPS": 20}
TERMINAL = {"DISARM": mav.MAV_CMD_COMPONENT_ARM_DISARM,
            "FLIGHTTERMINATION": mav.MAV_CMD_DO_FLIGHTTERMINATION}

NAME, REP = sys.argv[1], int(sys.argv[2])
ALT       = float(sys.argv[3])
TAG       = sys.argv[4]

R = Runner(f"V-{TAG}-{NAME}-{REP:02d}", branch="variance")
R.connect(); R.preflight(); R.takeoff(ALT)
R.setp("SIM_GPS1_JAM", 1)
R.wait("fsLand", timeout=120)
if NAME != "BASELINE":
    if NAME in MODES:      R.send_mode(NAME, MODES[NAME])
    elif NAME in TERMINAL: R.send_cmd(TERMINAL[NAME])
    else: raise SystemExit(f"알 수 없는 명령 {NAME}")
R.wait_end(timeout=220)
R.report()
