# -*- coding: utf-8 -*-
"""자동 생성됨 — 경로 SC-06 (분기 variance) / 생성물 id PENTEST-EX-0016.03-GNSS-VARIANCE-INJECT. 수정하지 말 것."""
import sys, os, time, json
# pymavlink 위치는 환경변수로 준다. 없으면 설치본을 쓴다.
_mav = os.environ.get("PYMAVLINK_PATH")
if _mav:
    sys.path.insert(0, _mav)
from pymavlink import mavutil
mav = mavutil.mavlink
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from runtime import Runner

R = Runner("SC-06", expected_outcome="destroy", branch="variance")
R.connect()
R.preflight()
R.takeoff(40.0)

R.setp("SIM_GPS1_JAM", 1)
R.observe("GPS_RAW_INT.fix_type")
R.wait("gnssLost")
R.observe("STATUSTEXT.text")
R.wait("navBranch")
R.wait("fsLand")
R.observe("HEARTBEAT.system_status")
R.wait("injectWindow")
R.send_mode("STABILIZE", 0)
R.observe("COMMAND_ACK.result")
R.wait("cmdAccepted")
R.wait("modeChanged")
R.wait("injectSucceeded")

R.wait_end()
R.report()
