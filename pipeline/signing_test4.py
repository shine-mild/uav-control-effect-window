# -*- coding: utf-8 -*-
"""서명 대조 실험 (4판) — 3판이 무효였던 원인을 제거한다.

3판이 무효인 이유 (2026-09-06 규명)
  서명 키는 기체의 영속 저장소에 남는다. GCS_Signing.cpp 의
  `_signing_storage(StorageManager::StorageKeys)` 에 저장되고 부팅마다
  `load_signing_key()` 로 다시 올라온다. 3판에서 처음으로 시동 **전** 설정이
  성공하자 키가 저장되었고, 그 뒤의 대조군(OFF)은 SITL 을 껐다 켜도 여전히
  서명이 걸린 기체에서 측정되었다. 그래서 대조군까지 주입이 막혔다.
  기록의 시각 순서가 이를 그대로 보여준다(S3-ON-01 이후 모든 OFF 가 실패).

4판 설계
  조건마다 시동 전에 기체의 서명 상태를 **명시적으로** 만든다.
    OFF : 32바이트 0 키와 타임스탬프 0 을 보낸다. load_signing_key() 는
          키·타임스탬프가 모두 0 이면 서명을 끈다(GCS_Signing.cpp:149-163).
    ON  : 32바이트 키를 보낸다.
  둘 다 STATUSTEXT 로 거부되지 않았음을 확인한 뒤 이륙한다.

  정상 GCS : SERIAL0 tcp 5760 = MAVLINK_COMM_0. 이 채널은 서명 여부와 무관하게
             수락된다(accept_unsigned_callback). 관측이 끊기지 않는 이유다.
  공격자   : SERIAL2 tcp 5763, source_system 99, 키 없음. 창 진입 전에 미리
             연결해 두어 관측 링크가 끊기지 않게 한다.

usage: signing_test4.py OFF|ON <반복번호>
"""
import sys, os, time, hashlib
os.environ["MAVLINK20"] = "1"
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.environ.get("PYMAVLINK_PATH", os.path.join(_AP, "modules", "mavlink")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil
from runtime import Runner, RESULT
mav = mavutil.mavlink

COND = (sys.argv[1] if len(sys.argv) > 1 else "OFF").upper()
REP  = int(sys.argv[2]) if len(sys.argv) > 2 else 1
SID  = f"S4-{COND}-{REP:02d}"
KEY  = hashlib.sha256(b"cisc-w26-signing-demo").digest()
ZERO = b"\x00" * 32
ALT_HOLD = 2
ATK_PORT = 5763
REJECT_MSG = "Won't setup signing when armed"
assert COND in ("OFF", "ON")


def main():
    g = Runner(SID, expected_outcome=None, branch="variance")
    g.connect()
    ts_ref = g.m.target_system, g.m.target_component

    # ---- 시동 전에 기체의 서명 상태를 만든다 ----
    n0 = len(g.events)
    if COND == "ON":
        ts = int((time.time() - 1420070400) * 100 * 1000)   # 2015-01-01 기준 10 us
        g.m.mav.setup_signing_send(ts_ref[0], ts_ref[1], KEY, ts)
    else:
        ts = 0
        g.m.mav.setup_signing_send(ts_ref[0], ts_ref[1], ZERO, 0)
    g.pump(2.0)
    rejected = any(REJECT_MSG in str(e.get("detail", "")) for e in g.events[n0:])
    if COND == "ON":
        # 기체가 모든 링크에 서명을 걸고 송신도 서명한다. 관측용 파서에도 같은 키를
        # 주지 않으면 텔레메트리를 읽지 못한다.
        g.m.setup_signing(KEY, sign_outgoing=True, initial_timestamp=ts,
                          allow_unsigned_callback=lambda _s, _m: True)
        g.pump(1.5)
    state = ("활성" if COND == "ON" else "해제") + ("(설정 거부됨)" if rejected else "")
    print(f"[i] 서명 {state} · 시동 전 설정 · 거부={rejected}", flush=True)
    if rejected:
        g.extra = dict(condition=COND, signing=state, setup_rejected=True, invalid=True)
        g.report(); return

    g.preflight()
    g.setp("SERIAL2_PROTOCOL", 2, critical=False)
    took_off = g.takeoff(40.0)

    # ---- 공격자 채널을 창 진입 전에 확보한다 ----
    atk = mavutil.mavlink_connection(f"tcp:127.0.0.1:{ATK_PORT}", source_system=99)
    atk.mav.heartbeat_send(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    hb = atk.wait_heartbeat(timeout=15)
    atk_ok = hb is not None
    # 기체가 서명 중이면 이 채널의 수신도 서명된다. 공격자는 키가 없으므로
    # 검증할 수 없다 — 그것이 이 실험의 조건이다. 수신은 열어 두고 판정은
    # 정상 GCS 의 관측(mode_after)으로 한다.
    print(f"[i] 공격자 채널 tcp:{ATK_PORT} 확립 {atk_ok} (미서명, source_system=99)", flush=True)

    g.setp("SIM_GPS1_JAM", 1)
    got = g.wait("fsLand", timeout=90)

    # 서명이 걸리면 공격자는 하트비트조차 검증하지 못할 수 있다. 그 경우에도
    # 명령은 보낸다 — 판정은 정상 GCS 가 관측한 모드 변화로 한다.
    ack = ack_dt = None
    a_s = hb.get_srcSystem() if hb is not None else ts_ref[0]
    atk.mav.command_long_send(a_s, 1, mav.MAV_CMD_DO_SET_MODE, 0,
                              1, ALT_HOLD, 0, 0, 0, 0, 0)
    t0 = time.time()
    while time.time() - t0 < 5.0:
        m = atk.recv_match(type="COMMAND_ACK", blocking=True, timeout=0.25)
        if m and m.command == mav.MAV_CMD_DO_SET_MODE:
            ack, ack_dt = m.result, round(time.time() - t0, 2); break
        g.pump(0.05)
    g.pump(2.5)

    mode_after = g.S["mode"]
    effective = (mode_after == "ALT_HOLD")
    g.extra = dict(condition=COND, signing=state, setup_rejected=rejected,
                   takeoff_ok=took_off, window_entered=got, attacker_channel_ok=atk_ok,
                   attacker_signed=False, attacker_source_system=99,
                   command="MAV_CMD_DO_SET_MODE(ALT_HOLD)",
                   ack=RESULT.get(ack, ack), ack_delay_s=ack_dt,
                   mode_after=mode_after, accepted=(ack == 0), effective=effective)
    print(f"\n[=] {SID} | 서명 {state} | 창진입 {got}")
    print(f"    COMMAND_ACK {RESULT.get(ack, ack)} ({ack_dt} s) · 실제 모드 {mode_after}"
          f" -> 주입 {'성립' if effective else '불성립'}", flush=True)
    g.wait_end(timeout=150)
    g.report()


main()
