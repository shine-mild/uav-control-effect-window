# -*- coding: utf-8 -*-
"""순항 중 교란 — 임무 수행 중인 기체를 공격할 수 있는가.

지금까지의 실험은 40 m 호버 상태에서 교란을 주었다. 실제 무인기는 임무 경로를
따라 이동 중일 때가 많다. 이동 중에도 같은 상태 전이가 일어나는지, 창의 길이가
달라지는지를 확인한다.

절차
  1) 웨이포인트 임무를 올린다 (이륙 -> 800 m 북쪽 -> 800 m 동쪽)
  2) AUTO 로 임무를 시작하고 기체가 순항 속도에 도달할 때까지 기다린다
  3) 순항 중(수평 속도가 임계 이상일 때) 교란을 주입한다
  4) 창의 길이와 이동 거리를 측정한다

usage: mission_test.py <이름> [run번호]
  BASELINE  : 주입 없음
  ALT_HOLD | STABILIZE | GUIDED_NOGPS | LOITER | RTL | DISARM
"""
import sys, os, time, json, math
os.environ["MAVLINK20"] = "1"
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.path.join(_AP, "modules", "mavlink"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil
from runtime import Runner, RESULT
mav = mavutil.mavlink

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = sys.argv[1] if len(sys.argv) > 1 else "BASELINE"
RUN = int(sys.argv[2]) if len(sys.argv) > 2 else 0
SID = f"MIS-{NAME}" + (f"-{RUN:02d}" if RUN else "")
HOME = (34.7604, 127.6622)
ALT = 40.0
CRUISE_MIN = 4.0            # 이 수평 속도(m/s)를 넘으면 순항으로 본다
MODES = {"STABILIZE": 0, "ALT_HOLD": 2, "LOITER": 5, "RTL": 6, "GUIDED_NOGPS": 20}
TERMINAL = {"DISARM": mav.MAV_CMD_COMPONENT_ARM_DISARM}


def offset(lat, lon, dn, de):
    """북/동 방향 미터 오프셋."""
    return lat + dn / 111320.0, lon + de / (111320.0 * math.cos(math.radians(lat)))


class MissionRunner(Runner):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.truth = None
        self.truth_at_jam = None
        self.gs = 0.0                       # 수평 속도
        self.gs_at_jam = None

    def _handle(self, msg):
        super()._handle(msg)
        t = msg.get_type()
        if t == 'SIMSTATE':
            self.truth = (msg.lat/1e7, msg.lng/1e7)
        elif t == 'GLOBAL_POSITION_INT':
            self.gs = math.hypot(msg.vx, msg.vy) / 100.0

    def upload_mission(self):
        wp1 = offset(*HOME, 800, 0)
        wp2 = offset(*HOME, 800, 800)
        items = [
            (mav.MAV_CMD_NAV_TAKEOFF, HOME[0], HOME[1], ALT),
            (mav.MAV_CMD_NAV_WAYPOINT, wp1[0], wp1[1], ALT),
            (mav.MAV_CMD_NAV_WAYPOINT, wp2[0], wp2[1], ALT),
        ]
        self.m.mav.mission_count_send(self.m.target_system, self.m.target_component,
                                      len(items), mav.MAV_MISSION_TYPE_MISSION)
        sent = 0
        d = time.time() + 20
        while sent < len(items) and time.time() < d:
            req = self.m.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'],
                                    blocking=True, timeout=3)
            if req is None: continue
            i = req.seq
            cmd, la, lo, al = items[i]
            self.m.mav.mission_item_int_send(
                self.m.target_system, self.m.target_component, i,
                mav.MAV_FRAME_GLOBAL_RELATIVE_ALT, cmd, 0, 1, 0, 0, 0, 0,
                int(la*1e7), int(lo*1e7), al, mav.MAV_MISSION_TYPE_MISSION)
            sent += 1
        ack = self.m.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
        ok = ack is not None and ack.type == 0
        if not ok:
            self.failures.append("임무 업로드 실패")
        print(f"[i] 임무 업로드 {sent}/{len(items)} 항목, ack={ok}", flush=True)
        return ok


def main():
    R = MissionRunner(SID, expected_outcome=None, branch="variance")
    R.connect()
    R.m.mav.command_long_send(R.m.target_system, R.m.target_component,
                              mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 164, 100000, 0, 0, 0, 0, 0)
    R.preflight()
    if not R.upload_mission():
        R.report(); return

    # GUIDED 로 이륙한 뒤 공중에서 AUTO 로 전환한다.
    # 지상에서 바로 AUTO 를 걸면 전환이 거부되어 기체가 시동만 걸린 채 자동 정지한다.
    R.takeoff(ALT)
    if R.failures:
        R.report(); return
    print(f"[i] 이륙 완료 — 고도 {R.S['alt']:.1f} m", flush=True)

    a = R._cmd(mav.MAV_CMD_DO_SET_MODE, 1, 3)          # AUTO
    R.pump(2)
    print(f"[i] AUTO 전환 ack={RESULT.get(a,a)} 모드={R.S['mode']}", flush=True)
    if R.S['mode'] != 'AUTO':
        R.failures.append(f"AUTO 전환 실패 (모드 {R.S['mode']})"); R.report(); return
    # 이륙 항목을 건너뛰고 첫 웨이포인트부터 수행
    R.m.mav.mission_set_current_send(R.m.target_system, R.m.target_component, 1)
    R.pump(2)
    print("[i] 임무 수행 시작 (웨이포인트 1)", flush=True)

    # 순항 도달까지 대기 (배속을 올려 대기 시간을 줄인다)
    R.setp('SIM_SPEEDUP', 3, critical=False)
    d = time.time() + 180
    while time.time() < d:
        R.pump(0.5)
        if R.S['alt'] >= ALT - 3 and R.gs >= CRUISE_MIN: break
    if R.gs < CRUISE_MIN:
        R.failures.append(f"순항 미도달 (gs={R.gs:.1f} m/s)")
    R.pump(5)
    R.setp('SIM_SPEEDUP', 1, critical=False); R.pump(2)
    R.chain.clear(); R.t_disarm = None

    # 순항 중 교란
    R.gs_at_jam = R.gs; R.truth_at_jam = R.truth
    R.alt_at_jam = R.S['alt']          # 반드시 주입 시점에 포착한다. 종료 후 값과 다르다.
    print(f"[i] 교란 주입 — 고도 {R.alt_at_jam:.1f} m, 수평속도 {R.gs:.1f} m/s, 모드 {R.S['mode']}", flush=True)
    R.setp("SIM_GPS1_JAM", 1)
    if not R.wait("fsLand", timeout=90):
        R.report(); return

    if NAME != "BASELINE":
        if NAME in MODES:      R.send_mode(NAME, MODES[NAME])
        elif NAME in TERMINAL: R.send_cmd(TERMINAL[NAME])
    R.wait_end(timeout=180)
    R.report()

    # 교란 시점 대비 이동 거리
    d_m = None
    if R.truth_at_jam and R.truth:
        a, b = R.truth_at_jam, R.truth
        RE = 6371000.0
        p1, p2 = math.radians(a[0]), math.radians(b[0])
        dp = math.radians(b[0]-a[0]); dl = math.radians(b[1]-a[1])
        h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        d_m = round(2*RE*math.asin(math.sqrt(h)), 2)

    p = os.path.join(HERE, "runs", f"{SID}.json")
    j = json.load(open(p, encoding="utf-8"))
    j["mission_experiment"] = dict(
        command=NAME, groundspeed_at_jam=round(R.gs_at_jam or 0, 2),
        alt_at_jam=round(R.alt_at_jam, 1),
        alt_at_observation_end=round(R.S['alt'], 1),
        truth_at_jam=R.truth_at_jam, truth_at_end=R.truth,
        displacement_from_jam_m=d_m)
    json.dump(j, open(p, "w"), ensure_ascii=False, indent=1)
    print(f"    순항속도 {R.gs_at_jam:.1f} m/s | 교란 후 이동 {d_m} m", flush=True)


if __name__ == "__main__":
    main()
