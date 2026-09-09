# -*- coding: utf-8 -*-
"""기록된 tlog 에서 조종 채널(RC3) 값을 센다. SITL 에 접속하지 않는다.

주 측정(R-*)과 시나리오 실행(SC-*)에서 조종 입력을 준 적이 없으므로,
그 구간의 스로틀이 실제로 무엇이었는지는 기록으로만 확인할 수 있다.

usage: PYTHONPATH=~/ardupilot/modules/mavlink python3 tools/check_rc_input.py
"""
import collections, glob, os, sys
from pymavlink import mavutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUPS = [("주 측정", "pipeline/tlogs/R-*.tlog"),
          ("시나리오 실행", "pipeline/tlogs/SC-*.tlog"),
          ("스로틀 대조 최하단", "pipeline/tlogs/RC-LOW-*.tlog"),
          ("스로틀 대조 중립", "pipeline/tlogs/RC-MID-*.tlog")]

for name, pat in GROUPS:
    files = sorted(glob.glob(os.path.join(HERE, pat)))
    if not files:
        print(f"{name}: 기록 없음"); continue
    total = collections.Counter()
    for f in files:
        m = mavutil.mavlink_connection(f)
        while True:
            msg = m.recv_match(type=['RC_CHANNELS', 'RC_CHANNELS_RAW'], blocking=False)
            if msg is None: break
            total[msg.chan3_raw] += 1
    print(f"{name}: 파일 {len(files)}건, RC3 분포 {dict(sorted(total.items()))}")
