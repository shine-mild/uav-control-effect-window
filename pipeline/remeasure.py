# -*- coding: utf-8 -*-
"""표 1 재측정 — 새 판정기(접지 기준, 순서 검사, 고도 기반 공중종료)로 12종 + 대조군.

분기는 variance (SIM_GPS1_JAM=1) 로 고정한다. posLost(완전 차단)에서는 무주입 대조군이
착륙을 감지하지 못해 비행이 종료되지 않으므로 창 w0 가 정의되지 않는다(runs_poslost 참조).
표 1·2·3 을 같은 기준으로 두기 위해 variance 로 통일한다.

usage: remeasure.py <NAME>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runtime import Runner
from pymavlink import mavutil
mav = mavutil.mavlink

MODES = {"STABILIZE":0, "ALT_HOLD":2, "AUTO":3, "GUIDED":4, "LOITER":5,
         "RTL":6, "POSHOLD":16, "BRAKE":17, "GUIDED_NOGPS":20, "SMART_RTL":21}
TERMINAL = {"FLIGHTTERMINATION": mav.MAV_CMD_DO_FLIGHTTERMINATION,
            "DISARM": mav.MAV_CMD_COMPONENT_ARM_DISARM}
# 사전 분류(가설). 판정은 관측으로 한다.
EXPECT = {"STABILIZE":"destroy", "ALT_HOLD":"recover", "GUIDED_NOGPS":"recover",
          "FLIGHTTERMINATION":"destroy", "DISARM":"destroy"}

NAME = sys.argv[1]
R = Runner(f"M-{NAME}", expected_outcome=EXPECT.get(NAME), branch="variance")
R.connect(); R.preflight(); R.takeoff(40.0)
R.setp("SIM_GPS1_JAM", 1)             # variance 분기
R.wait("fsLand", timeout=90)
if NAME != "BASELINE":
    if NAME in MODES:      R.send_mode(NAME, MODES[NAME])
    elif NAME in TERMINAL: R.send_cmd(TERMINAL[NAME])
    else: raise SystemExit(f"알 수 없는 명령 {NAME}")
R.wait_end()
R.report()
