# -*- coding: utf-8 -*-
"""서명 ON/OFF 실험 (3판) — 2판의 무효 원인을 제거한다.

2판이 무효인 이유
  이륙(=armed) 이후에 SETUP_SIGNING 을 보냈다. ArduPilot 은 armed 상태의
  서명 설정을 거부한다(GCS_Signing.cpp:76-77 "ERROR: Won't setup signing
  when armed"). 실제로 SIGN-ON 30회 전부에 이 오류가 기록되어 있다.
  더욱이 관측용 GCS 파서에만 서명을 걸어 기체의 미서명 텔레메트리를 받지
  못하게 되었고, 그 결과 창과 비행 종료가 관측되지 않았다. 기록된
  mode_after=LAND 는 관측이 끊기기 직전의 값이다.

3판 설계
  서명을 **시동 전에** 설정하고, 설정이 거부되지 않았음을 STATUSTEXT 로
  확인한 뒤에 이륙한다. 관측용 GCS 는 송신에 서명을 붙여 기체와의 통신을
  유지한다. 공격자는 SERIAL2 에서 키 없이 명령을 보낸다.

  정상 GCS : SERIAL0 tcp 5760, source_system 250, 서명 키 보유
  공격자   : SERIAL2 tcp 5763, source_system  99, 서명 키 없음
  순서     : 연결 -> (ON 이면) 서명 설정·검증 -> 이륙 -> 교란 -> 창 진입
             -> 공격자 주입 -> 종료 관측

usage: signing_test3.py OFF|ON [반복번호]
"""
import sys, os, time, hashlib
os.environ["MAVLINK20"] = "1"
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.path.join(_AP, "modules", "mavlink"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil
from runtime import Runner, RESULT
mav = mavutil.mavlink

COND = (sys.argv[1] if len(sys.argv) > 1 else "OFF").upper()
REP  = int(sys.argv[2]) if len(sys.argv) > 2 else 1
SID  = f"S3-{COND}-{REP:02d}"
KEY  = hashlib.sha256(b"cisc-w26-signing-demo").digest()
ALT_HOLD = 2
ATK_PORT = 5763

REJECT_MSG = "Won't setup signing when armed"


def attacker_connect(timeout=25):
    a = mavutil.mavlink_connection(f'tcp:127.0.0.1:{ATK_PORT}', source_system=99)
    a.mav.heartbeat_send(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    if a.wait_heartbeat(timeout=timeout) is None:
        return None, None, None
    return a, a.target_system, a.target_component


def main():
    gcs = Runner(SID, expected_outcome=None, branch="variance")
    gcs.connect()
    tgt_s, tgt_c = gcs.m.target_system, gcs.m.target_component

    # ---- 서명 정책을 시동 전에 적용한다 ----
    signing_state = "미적용"
    setup_rejected = None
    if COND == "ON":
        n_before = len(gcs.events)
        # MAVLink 서명 타임스탬프는 2015-01-01 기준 10 마이크로초 단위이다.
        # 기체와 GCS 에 같은 규약의 값을 주지 않으면 재생 방지 규칙에 걸려
        # 기체가 GCS 의 서명 명령을 전부 버린다.
        ts = int((time.time() - 1420070400) * 100 * 1000)
        gcs.m.mav.setup_signing_send(tgt_s, tgt_c, KEY, ts)
        gcs.pump(2.0)
        # 기체가 거부했는지 STATUSTEXT 로 확인한다
        setup_rejected = any(REJECT_MSG in str(e.get("detail", ""))
                             for e in gcs.events[n_before:])
        # 송신에는 서명을 붙이되, 수신은 서명 여부와 무관하게 받는다.
        # 관측자가 눈이 머는 것을 막기 위한 조치이며, 기체가 공격자의 미서명
        # 명령을 어떻게 처리하는지에는 영향을 주지 않는다.
        gcs.m.setup_signing(KEY, sign_outgoing=True, initial_timestamp=ts,
                            allow_unsigned_callback=lambda _s, _m: True)
        gcs.pump(2.0)
        signing_state = "활성" if not setup_rejected else "설정 거부됨"
    print(f"[i] 서명 상태: {signing_state} (시동 전 설정, 거부={setup_rejected})", flush=True)
    if COND == "ON" and setup_rejected:
        print("[!] 서명 설정이 거부되었다 — 이 실행은 무효다.", flush=True)
        gcs.report(); return

    gcs.preflight()
    gcs.setp('SERIAL2_PROTOCOL', 2, critical=False)
    ok = gcs.takeoff(40.0)
    if not ok:
        print("[!] 이륙 실패 — 서명 적용 후 명령이 전달되지 않았을 수 있다.", flush=True)

    gcs.setp("SIM_GPS1_JAM", 1)
    got_window = gcs.wait("fsLand", timeout=90)

    # ---- 공격자 주입 (미서명) ----
    gcs.pump(0.3)                      # 관측 링크를 끊기지 않게 유지한다
    atk, a_s, a_c = attacker_connect(timeout=10)
    ack = ack_dt = None
    if atk is None:
        print("[!] 공격자 채널 확립 실패", flush=True); atk_ok = False
    else:
        atk_ok = True
        atk.mav.command_long_send(a_s, a_c, mav.MAV_CMD_DO_SET_MODE, 0,
                                  1, ALT_HOLD, 0, 0, 0, 0, 0)
        t0 = time.time()
        while time.time() - t0 < 5.0:
            m = atk.recv_match(type='COMMAND_ACK', blocking=True, timeout=0.3)
            if m and m.command == mav.MAV_CMD_DO_SET_MODE:
                ack, ack_dt = m.result, round(time.time() - t0, 2); break
        gcs.pump(2.5)

    mode_after = gcs.S['mode']
    effective = (mode_after == 'ALT_HOLD')
    gcs.extra = dict(condition=COND, signing=signing_state,
                     setup_rejected=setup_rejected, takeoff_ok=ok,
                     window_entered=got_window, attacker_channel_ok=atk_ok,
                     ack=RESULT.get(ack, ack), ack_delay_s=ack_dt,
                     mode_after=mode_after, effective=effective)
    print(f"\n[=] {SID} | 서명 {signing_state} | 창진입 {got_window}")
    print(f"    COMMAND_ACK  {RESULT.get(ack, ack)} ({ack_dt} s)")
    print(f"    실제 모드    {mode_after} -> 주입 {'성립' if effective else '불성립'}")
    gcs.wait_end(timeout=120)
    gcs.report()


main()
