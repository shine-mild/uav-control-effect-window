# -*- coding: utf-8 -*-
"""자동 생성됨 — 경로 SC-05 (분기 posLost) / 생성물 id EX-0016.03. 수정하지 말 것."""
import sys, os, time, json
# pymavlink 위치는 환경변수로 준다. 없으면 설치본을 쓴다.
_mav = os.environ.get("PYMAVLINK_PATH")
if _mav:
    sys.path.insert(0, _mav)
from pymavlink import mavutil
mav = mavutil.mavlink
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from runtime import Runner

R = Runner("SC-05", expected_outcome="destroy", branch="posLost")
R.connect()
R.preflight()
R.takeoff(40.0)

R.setp("SIM_GPS1_ENABLE", 0)
R.observe("GPS_RAW_INT.fix_type")
R.wait("gnssLost")
R.observe("STATUSTEXT")
R.wait("navBranch")
R.observe("HEARTBEAT.system_status")
R.wait("fsLand")
R.wait("injectWindow")
R.send_cmd(mav.MAV_CMD_COMPONENT_ARM_DISARM)
R.observe("COMMAND_ACK.result")
R.wait("cmdAccepted")
R.wait("injectSucceeded")

R.wait_end()
R.report()
