# -*- coding: utf-8 -*-
"""반복 측정 — 사전 등록한 설계에 따라 조건 하나를 한 번 수행한다.
결과는 runs/R-{NAME}-{rep}.json 으로 남긴다 (기존 M-* 를 덮지 않는다).

usage: repeat.py <NAME> <rep>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runtime import Runner
from pymavlink import mavutil
mav = mavutil.mavlink

MODES    = {"STABILIZE": 0, "ALT_HOLD": 2, "LOITER": 5}
TERMINAL = {"DISARM": mav.MAV_CMD_COMPONENT_ARM_DISARM}
EXPECT   = {"STABILIZE": "destroy", "ALT_HOLD": "recover", "DISARM": "destroy"}

NAME = sys.argv[1]
REP  = int(sys.argv[2])
R = Runner(f"R-{NAME}-{REP:02d}", expected_outcome=EXPECT.get(NAME), branch="variance")
R.connect(); R.preflight(); R.takeoff(40.0)
R.setp("SIM_GPS1_JAM", 1)                 # variance 분기로 고정
R.wait("fsLand", timeout=90)
if NAME != "BASELINE":
    if NAME in MODES:      R.send_mode(NAME, MODES[NAME])
    elif NAME in TERMINAL: R.send_cmd(TERMINAL[NAME])
    else: raise SystemExit(f"알 수 없는 명령 {NAME}")
R.wait_end()
R.report()
