# -*- coding: utf-8 -*-
"""자동 생성됨 — 경로 SC-08 (분기 variance) / 생성물 id EX-0016.03. 수정하지 말 것."""
import sys, os, time, json
_mav = os.environ.get("PYMAVLINK_PATH")
if _mav:
    sys.path.insert(0, _mav)
from pymavlink import mavutil
mav = mavutil.mavlink
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from runtime import Runner

R = Runner("SC-08", expected_outcome="extend", branch="variance")
R.connect()
R.preflight()
R.takeoff(40.0)

R.setp("SIM_GPS1_JAM", 1)
R.observe("GPS_RAW_INT.fix_type")
R.wait("gnssLost")
R.observe("STATUSTEXT")
R.wait("ekfVarExceeded")
R.observe("EKF_STATUS_REPORT.flags")
R.wait("navDegraded")
R.observe("HEARTBEAT.custom_mode")
R.wait("fsLand")
R.observe("COMMAND_ACK.result")
R.wait("injectWindow")
R.send_mode("GUIDED_NOGPS", 20)
R.observe("COMMAND_ACK.result")
R.observe("HEARTBEAT.custom_mode")

R.wait_end()
R.report()
