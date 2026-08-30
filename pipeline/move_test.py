# -*- coding: utf-8 -*-
"""항법 상실 상태에서 기체를 이동시킬 수 있는가.

배경
  표 1 에서 위치 기반 모드(LOITER/GUIDED/RTL/AUTO/...)는 모두 거부되었다.
  좌표를 지정하는 유도는 불가능하다는 뜻이다. 그러나 GUIDED_NOGPS 는 수락되었다.
  이 모드는 좌표 대신 자세와 추력을 직접 지령한다. 기울이면 그 방향으로 밀려간다.
  실제로 이동이 일어나는지, 얼마나 가는지를 측정한다.

측정
  위치는 SITL 참값(SIMSTATE.lat/lng)으로 잰다. GPS 가 죽어 있으므로 EKF 추정치는
  쓸 수 없다. 교란 시점의 참 위치와 비행 종료 시점의 참 위치 사이 거리를 잰다.

조건
  DRIFT : GUIDED_NOGPS 로 전환만 하고 지령을 주지 않는다 (대조군)
  PUSH  : GUIDED_NOGPS 로 전환한 뒤 기수를 15도 숙여 전진 지령을 준다

usage: move_test.py DRIFT|PUSH [run번호]
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
COND = (sys.argv[1] if len(sys.argv) > 1 else "PUSH").upper()
RUN  = int(sys.argv[2]) if len(sys.argv) > 2 else 0
SID  = f"MOVE-{COND}" + (f"-{RUN:02d}" if RUN else "")
GUIDED_NOGPS = 20
PITCH_DEG = -15.0          # 음수 = 기수 숙임 = 전진
THRUST = 0.5               # 0.5 ≈ 호버


def euler_to_q(roll, pitch, yaw):
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    return [cr*cp*cy + sr*sp*sy, sr*cp*cy - cr*sp*sy,
            cr*sp*cy + sr*cp*sy, cr*cp*sy - sr*sp*cy]


def dist_m(a, b):
    """(lat,lng) 도 단위 두 점 사이 거리(m)."""
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0]-a[0]); dl = math.radians(b[1]-a[1])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(h))


def bearing(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1]-a[1])
    y = math.sin(dl)*math.cos(p2)
    x = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


class MoveRunner(Runner):
    """SITL 참값 위치를 추가로 기록한다."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.truth = None          # 최신 참 위치 (lat, lng)
        self.truth_at_land = None
        self.truth_track = []
        self.yaw = 0.0

    def _handle(self, msg):
        super()._handle(msg)
        if msg.get_type() == 'SIMSTATE':
            self.truth = (msg.lat/1e7, msg.lng/1e7)
            self.yaw = msg.yaw
            self.truth_track.append((self.S['simms']/1000.0,
                                     self.truth[0], self.truth[1], self.S['alt']))
            if self.t_land is not None and self.truth_at_land is None:
                self.truth_at_land = self.truth


def main():
    R = MoveRunner(SID, expected_outcome=None, branch="variance")
    R.connect()
    # SIMSTATE(164) 를 10 Hz 로 요청 — 참값 위치
    R.m.mav.command_long_send(R.m.target_system, R.m.target_component,
                              mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                              164, 100000, 0, 0, 0, 0, 0)
    R.preflight(); R.takeoff(40.0)
    R.setp("SIM_GPS1_JAM", 1)
    if not R.wait("fsLand", timeout=90):
        R.report(); return
    start = R.truth_at_land or R.truth
    alt_at_land = R.S['alt']
    print(f"[i] 창 진입 — 참 위치 {start}, 고도 {alt_at_land:.1f} m", flush=True)

    # GUIDED_NOGPS 로 전환
    R.send_mode("GUIDED_NOGPS", GUIDED_NOGPS)
    if R.S['mode'] != 'GUIDED_NOGPS':
        print(f"[!] 모드 전환 실패 (현재 {R.S['mode']})", flush=True)

    # 지령 전송 — ArduPilot 은 자세 지령이 끊기면 곧 무효로 본다. 계속 보낸다.
    sent = 0
    if COND == "PUSH":
        q = euler_to_q(0.0, math.radians(PITCH_DEG), R.yaw)
        t_end = time.time() + 25.0
        while time.time() < t_end and R.S['armed'] and R.S['alt'] > 2.0:
            R.m.mav.set_attitude_target_send(
                int(R.S['simms']), R.m.target_system, R.m.target_component,
                0b00000111,                      # 각속도 무시, 자세+추력 사용
                q, 0, 0, 0, THRUST)
            sent += 1
            R.pump(0.1)
        print(f"[i] 자세 지령 {sent}회 전송 (기수 {PITCH_DEG}도, 추력 {THRUST})", flush=True)
    else:
        R.pump(25.0)
        print("[i] 대조군 — 지령 없이 표류만 관찰", flush=True)

    R.wait_end(timeout=150)
    end = R.truth
    d = dist_m(start, end) if (start and end) else None
    b = bearing(start, end) if (start and end) else None

    R.report()
    p = os.path.join(HERE, "runs", f"{SID}.json")
    j = json.load(open(p, encoding="utf-8"))
    j["move_experiment"] = dict(
        condition=COND, pitch_deg=(PITCH_DEG if COND == "PUSH" else None),
        thrust=(THRUST if COND == "PUSH" else None), attitude_cmds_sent=sent,
        mode_after=R.S['mode'], truth_at_land=start, truth_at_end=end,
        displacement_m=(round(d, 2) if d is not None else None),
        bearing_deg=(round(b, 1) if b is not None else None),
        alt_at_land=round(alt_at_land, 1))
    j["truth_track"] = R.truth_track
    json.dump(j, open(p, "w"), ensure_ascii=False, indent=1)

    print(f"\n[=] 이동 실험 {COND}")
    print(f"    모드            {R.S['mode']}")
    print(f"    자세 지령       {sent}회")
    print(f"    수평 이동거리   {d:.2f} m" if d is not None else "    수평 이동거리   측정 실패")
    print(f"    이동 방위       {b:.1f}도" if b is not None else "")
    print(f"    창              {j.get('window_s')} s")


if __name__ == "__main__":
    main()
