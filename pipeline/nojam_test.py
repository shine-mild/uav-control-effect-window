# -*- coding: utf-8 -*-
"""무재밍 대조군 — 재밍이 없을 때 운용자의 회수 명령이 수락되는지 확인한다.

논문은 "재밍이 더하는 것은 새로운 공격 수단이 아니라 복구의 차단"이라고 주장한다.
그 주장은 재밍 없는 조건과의 비교를 요구하는데 기존 실행에는 그 조건이 없었다.
이 스크립트가 그 왼쪽 열을 만든다.

usage: nojam_test.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runtime import Runner

MODES = {"ALT_HOLD": 2, "RTL": 6, "LOITER": 5, "POSHOLD": 16}

R = Runner("NJ-RECOVERY-01", branch="nojam")
R.connect()
R.preflight()          # SIM_GPS1_JAM = 0 이 여기서 설정된다
R.takeoff(40.0)

# 공격자 주입 — 재밍 없이
R.send_mode("ALT_HOLD", MODES["ALT_HOLD"])
R.pump(3)

# 운용자 회수 시도 — 재밍 상태에서 거부되던 세 종
for name in ("RTL", "LOITER", "POSHOLD"):
    R.send_mode(name, MODES[name])
    R.pump(3)

R.report()
