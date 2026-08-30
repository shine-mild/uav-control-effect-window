# -*- coding: utf-8 -*-
"""자동 생성됨 — 경로 SC-06 (분기 variance) / 생성물 id EX-0016.03-gnssArtifact-cmdInject-stabilize. 수정하지 말 것."""
import sys, os, time, json
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

R.setp("FS_EKF_ACTION", 1)
R.setp("EK3_OPTIONS", 0)
R.setp("SIM_GPS1_JAM", 1)
R.observe("GPS_RAW_INT.fix_type")
R.observe("STATUSTEXT")
R.wait("ekfVarExceeded")
R.observe("HEARTBEAT.system_status")
R.wait("fsLand")
R.send_mode("STABILIZE", 0)
R.observe("COMMAND_ACK")
R.observe("HEARTBEAT.custom_mode")
R.observe("GLOBAL_POSITION_INT")

R.wait_end()
R.report()
