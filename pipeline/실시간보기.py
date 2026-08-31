# -*- coding: utf-8 -*-
"""실시간 관제 화면 — 설치 없이 터미널에서 기체 상태를 본다.

실험 스크립트는 SERIAL0(5760)을 쓰고, 이 화면은 SERIAL1(5762)로 붙는다.
따라서 실험을 돌리는 중에 다른 창에서 켜 두면 실시간으로 관찰할 수 있다.

사용법
  창 1:  ~/실험.sh ALT_HOLD
  창 2:  python3 실시간보기.py

Ctrl+C 로 종료.
"""
import sys, os, time
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.path.join(_AP, "modules", "mavlink"))
from pymavlink import mavutil
mav = mavutil.mavlink

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5762
BAR_W = 34
ALT_MAX = 45.0

print(f"tcp:127.0.0.1:{PORT} 연결 대기...", flush=True)
m = mavutil.mavlink_connection(f'tcp:127.0.0.1:{PORT}', source_system=200)
m.mav.heartbeat_send(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
m.wait_heartbeat(timeout=60)
m.mav.request_data_stream_send(m.target_system, m.target_component,
                               mav.MAV_DATA_STREAM_ALL, 10, 1)
print("연결됨. Ctrl+C 로 종료.\n", flush=True)

S = dict(mode="?", alt=0.0, fix=0, sats=0, armed=False, simms=0, vz=0.0)
_mm = None
events = []


def modename(cm):
    global _mm
    if _mm is None:
        try: _mm = {v: k for k, v in m.mode_mapping().items()}
        except Exception: _mm = {}
    return _mm.get(cm, str(cm))


def draw():
    filled = int(max(0.0, min(1.0, S['alt'] / ALT_MAX)) * BAR_W)
    bar = "█" * filled + "·" * (BAR_W - filled)
    gps = {0: "없음", 1: "없음", 2: "2D", 3: "3D"}.get(S['fix'], str(S['fix']))
    armed = "시동" if S['armed'] else "정지"
    line = (f"\r  t={S['simms']/1000:7.1f}s  [{bar}] {S['alt']:6.1f}m "
            f"{S['vz']:+5.1f}m/s │ {S['mode']:<13} │ GPS {gps:<4} {S['sats']:2d}기 │ {armed}  ")
    sys.stdout.write(line); sys.stdout.flush()


def event(txt):
    sys.stdout.write("\r" + " " * 110 + "\r")
    print(f"  ★ [{S['simms']/1000:7.1f}s] {txt}", flush=True)


try:
    last = 0.0
    while True:
        msg = m.recv_match(blocking=True, timeout=1.0)
        if msg is None:
            draw(); continue
        if msg.get_srcSystem() != m.target_system:
            continue
        t = msg.get_type()
        if t == 'GLOBAL_POSITION_INT':
            S['simms'] = msg.time_boot_ms
            S['alt'] = msg.relative_alt / 1000.0
            S['vz'] = -msg.vz / 100.0
        elif t == 'GPS_RAW_INT':
            if S['fix'] >= 3 and msg.fix_type <= 1:
                event("GPS 상실 — 교란 시작")
            S['fix'], S['sats'] = msg.fix_type, msg.satellites_visible
        elif t == 'HEARTBEAT':
            a = bool(msg.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
            if S['armed'] and not a:
                event(f"시동 정지 — 고도 {S['alt']:.1f} m"
                      + ("  ← 공중 종료" if S['alt'] > 3 else ""))
            S['armed'] = a
            nm = modename(msg.custom_mode)
            if nm != S['mode']:
                if S['mode'] != "?":
                    event(f"모드 전환  {S['mode']} → {nm}"
                          + ("   ← 강제 착륙 진입, 창 시작" if nm == "LAND" else ""))
                S['mode'] = nm
        elif t == 'STATUSTEXT':
            s = msg.text.strip()
            for key, tag in (('EKF variance', 'EKF 이상'), ('Hit ground', '접지'),
                             ('requires position', '명령 거부'), ('Failsafe', 'Failsafe')):
                if key in s:
                    event(f"{tag}: {s}"); break
        if time.time() - last > 0.2:
            draw(); last = time.time()
except KeyboardInterrupt:
    print("\n\n종료.")
