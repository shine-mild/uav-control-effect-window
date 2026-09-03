# -*- coding: utf-8 -*-
"""자동 생성됨 — 경로 SC-07 (분기 variance) / 생성물 id EX-0016.03. 수정하지 말 것."""
import sys, os, time, json
# pymavlink 위치는 환경변수로 준다. 없으면 설치본을 쓴다.
_mav = os.environ.get("PYMAVLINK_PATH")
if _mav:
    sys.path.insert(0, _mav)
from pymavlink import mavutil
mav = mavutil.mavlink
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from runtime import Runner

R = Runner("SC-07", expected_outcome="recover", branch="variance")
R.connect()
R.preflight()
R.takeoff(40.0)

R.setp("SIM_GPS1_JAM", 1)
R.observe("GPS_RAW_INT.fix_type")
R.wait("gnssLost")
R.wait("navBranch")
R.observe("STATUSTEXT.text")
R.wait("fsLand")
R.wait("injectWindow")
R.send_mode("ALT_HOLD", 2)
R.observe("COMMAND_ACK.result")
R.wait("cmdAccepted")
R.observe("HEARTBEAT.custom_mode")
R.wait("modeChanged")
R.wait("injectSucceeded")

R.wait_end()
R.report()
