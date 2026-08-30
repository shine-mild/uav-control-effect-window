# -*- coding: utf-8 -*-
"""서명 ON/OFF 실험 (개정 2판) — noSigning 전제조건의 증거를 만든다.

1판 실패 원인
  SERIAL0(5760) 은 단일 접속만 받아 공격자 연결이 정상 GCS 를 밀어냈다.
  또한 서명을 비행 준비 이전에 켜서 정상 GCS 자신의 파라미터 설정이 실패했다.

2판 설계
  정상 GCS : SERIAL0 tcp 5760, source_system = 250
  공격자   : SERIAL2 tcp 5763, source_system =  99, 서명 키 없음
  순서     : 이륙 -> 교란 -> 창 진입 -> (ON 이면) 서명 활성화 -> 공격자 주입

  서명을 창 진입 직후에 켜는 이유는 비행 준비 절차와 서명 정책을 분리하여
  측정 대상을 "미서명 외부 명령의 수락 여부" 하나로 좁히기 위해서다.

공격자 모델
  공격자는 격리된 시험망에서 별도 MAVLink 종단에 도달할 수 있으나
  서명 키와 정상 GCS 자격을 보유하지 않는다.

usage: signing_test.py OFF | ON
"""
import sys, os, time, json, hashlib
os.environ["MAVLINK20"] = "1"          # v1 에는 서명 기능이 없다
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.path.join(_AP, "modules", "mavlink"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil
from runtime import Runner, RESULT
mav = mavutil.mavlink

HERE = os.path.dirname(os.path.abspath(__file__))
COND = (sys.argv[1] if len(sys.argv) > 1 else "OFF").upper()
KEY = hashlib.sha256(b"cisc-w26-signing-demo").digest()
ALT_HOLD = 2
ATK_PORT = 5763                         # SERIAL2


def attacker_connect(timeout=25):
    """공격자 채널 확립. 스트림을 요청하고 하트비트를 확인한다."""
    a = mavutil.mavlink_connection(f'tcp:127.0.0.1:{ATK_PORT}', source_system=99)
    a.mav.heartbeat_send(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    hb = a.wait_heartbeat(timeout=timeout)
    if hb is None:
        return None, None, None
    return a, a.target_system, a.target_component


def main():
    gcs = Runner(f"SIGN-{COND}", expected_outcome=None, branch="variance")
    gcs.connect()
    gcs.preflight()
    # 공격자 채널을 MAVLink2 로 둔다 (기본값이나 명시한다)
    gcs.setp('SERIAL2_PROTOCOL', 2, critical=False)
    gcs.takeoff(40.0)
    tgt_s, tgt_c = gcs.m.target_system, gcs.m.target_component

    # ---- 교란 주입 후 창 진입 ----
    gcs.setp("SIM_GPS1_JAM", 1)
    got_window = gcs.wait("fsLand", timeout=90)

    # ---- 서명 정책 적용 ----
    signing_state = "미적용"
    if COND == "ON":
        gcs.m.mav.setup_signing_send(tgt_s, tgt_c, KEY, int(time.time() * 1e5))
        gcs.pump(1.5)
        gcs.m.setup_signing(KEY, sign_outgoing=True)
        gcs.pump(1.5)
        signing_state = "활성 (정상 GCS 만 키 보유)"
    print(f"[i] 서명 상태: {signing_state} | 창 진입 {got_window}", flush=True)

    # ---- 공격자 주입 ----
    atk, a_s, a_c = attacker_connect()
    if atk is None:
        print("[!] 공격자 채널 확립 실패 (SERIAL2 하트비트 없음)", flush=True)
        ack, ack_dt, mode_after = None, None, gcs.S['mode']
        atk_ok = False
    else:
        atk_ok = True
        print(f"[i] 공격자 채널 확립 tcp:{ATK_PORT} (source_system=99, 미서명)", flush=True)
        atk.mav.command_long_send(a_s, a_c, mav.MAV_CMD_DO_SET_MODE, 0,
                                  1, ALT_HOLD, 0, 0, 0, 0, 0)
        t0 = time.time(); ack = ack_dt = None
        while time.time() - t0 < 5.0:
            m = atk.recv_match(type='COMMAND_ACK', blocking=True, timeout=0.3)
            if m and m.command == mav.MAV_CMD_DO_SET_MODE:
                ack, ack_dt = m.result, round(time.time() - t0, 2); break
        gcs.pump(2.5)
        mode_after = gcs.S['mode']

    accepted = (ack == 0)
    effective = (mode_after == 'ALT_HOLD')
    print(f"\n[=] 조건 {COND} | 서명 {signing_state}")
    print(f"    공격자 채널        tcp:{ATK_PORT}  확립 {atk_ok}")
    print(f"    명령               DO_SET_MODE(ALT_HOLD)  미서명, source_system=99")
    print(f"    COMMAND_ACK        {RESULT.get(ack, ack)}  (응답 {ack_dt} s)")
    print(f"    실제 모드          {mode_after}  -> 주입 {'성립' if effective else '불성립'}")

    gcs.wait_end(timeout=120)
    gcs.report()

    p = os.path.join(HERE, "runs", f"SIGN-{COND}.json")
    j = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    j["signing_experiment"] = dict(
        condition=COND, signing=signing_state, attacker_channel=f"tcp:{ATK_PORT}",
        attacker_source_system=99, attacker_signed=False,
        attacker_channel_ok=atk_ok, window_entered=got_window,
        command="MAV_CMD_DO_SET_MODE(ALT_HOLD)",
        ack=RESULT.get(ack, str(ack)), ack_delay_s=ack_dt,
        mode_after=mode_after, accepted=accepted, effective=effective)
    json.dump(j, open(p, "w"), ensure_ascii=False, indent=1)
    print(f"[+] 기록: {p}")


if __name__ == "__main__":
    main()
