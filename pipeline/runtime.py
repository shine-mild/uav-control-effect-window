# -*- coding: utf-8 -*-
"""자동 생성 시나리오의 실행·판정 런타임 (개정판).

2026-08-26 외부 검토 반영:
  ① grounded(armed=0) 는 착륙이 아니다 -> motorsDisarmed / landed / terminatedInAir 로 분리.
     ⚠ landed_state 는 시동정지 시 ON_GROUND 로 바뀌므로 공중 종료 판정에 쓸 수 없다.
     공중 종료는 시동정지 시점의 상대고도로 판정한다(AIR_ALT_MIN).
  ② wait() 시간초과를 실패로 처리한다. 전제조건 불성립 상태로 다음 단계에 진입하지 않는다.
  ③ linkAlive 를 실제로 검증한다(HEARTBEAT 수신 간격).
  ④ 상태 사슬을 순서까지 검사한다. 단 수신 순서가 아니라 시뮬레이션 시각으로 정렬한다.
  ⑤ 파라미터 설정 실패(PARAM_VALUE 미수신 또는 값 불일치)를 실패로 처리한다.
"""
import sys, time, json, os, hashlib, subprocess, datetime
_AP = os.environ.get("ARDUPILOT_PATH", os.path.expanduser("~/ardupilot"))
sys.path.insert(0, os.path.join(_AP, "modules", "mavlink"))
from pymavlink import mavutil
mav = mavutil.mavlink

BASELINE_W = 48.35          # 대조군 창 (초)
IMPACT_DESTROY = 5.0        # 접지 속도 파괴 임계 (m/s)
RESULT = {0: "ACCEPTED", 1: "TEMPORARILY_REJECTED", 2: "DENIED",
          3: "UNSUPPORTED", 4: "FAILED", 5: "IN_PROGRESS", 6: "CANCELLED"}
HB_GAP_MAX = 3.0            # 이 시간 이상 HEARTBEAT 단절이면 linkAlive 불성립 (실시간 초)
AIR_ALT_MIN = 10.0          # 시동정지 시 이 고도를 넘으면 공중 종료 (m)
# 항법 상실 상태에서는 EKF 고도 추정이 어긋난다. 실측에서 정상 착륙 후 시동정지 시점의
# 보고 고도가 3.9~6.6 m 였고 실제 공중 종료는 39.6 m 였다. 임계를 10 m 로 둔다.

# 예측 사슬 — 순서까지 이 순열로 관측되어야 재현으로 인정한다
EXPECTED_CHAIN = ["gnssLost", "navBranch", "fsLand", "cmdAccepted", "flightEnd"]
ORDER_TOL_MS = 500          # 동일 사건의 메시지 도착 편차 허용 (ms)


class Runner:
    def __init__(self, sid, expected_outcome=None, branch=None):
        self.sid = sid
        self.expected = expected_outcome
        self.branch = branch                 # "variance" | "posLost"
        self.S = dict(mode=None, armed=False, alt=0.0, fix=0, sats=0,
                      simms=0, impact=None, landed=0)
        self.chain = []                      # [(술어, sim_ms)]
        self.acks = []
        self.failures = []                   # 하나라도 있으면 ok=False
        self.t_land = None
        self.t_cmd = None
        self.t_disarm = None
        self.t_onground = None
        self.terminated_in_air = None
        self.alt_at_disarm = None
        self.last_hb = None
        self.hb_gap_max = 0.0
        self._modemap = None
        self.events = []                  # 원시 STATUSTEXT 보존 (재현 검증용)
        self.tlog_path = None             # 원시 MAVLink tlog 경로

    # ------------------------------------------------ 연결
    def connect(self, dev='tcp:127.0.0.1:5760'):
        self.m = mavutil.mavlink_connection(dev, source_system=255)
        _here = os.path.dirname(os.path.abspath(__file__))
        _ld = os.path.join(_here, 'tlogs'); os.makedirs(_ld, exist_ok=True)
        self.tlog_path = os.path.join(_ld, self.sid + '.tlog')
        try:
            self.m.setup_logfile(self.tlog_path)   # 원시 MAVLink 보존
        except Exception as e:
            self.tlog_path = None
            print(f'    [!] tlog 개시 실패: {e}', flush=True)
        self.m.wait_heartbeat(timeout=90)
        self.m.mav.request_data_stream_send(
            self.m.target_system, self.m.target_component,
            mav.MAV_DATA_STREAM_ALL, 20, 1)
        # EXTENDED_SYS_STATE(245) 를 5 Hz 로 요청 — 착륙 판정에 필요
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                     245, 200000, 0, 0, 0, 0, 0)
        print(f"[+] {self.sid} 연결 (분기 {self.branch})", flush=True)

    def _modename(self, cm):
        if self._modemap is None:
            try: self._modemap = {v: k for k, v in self.m.mode_mapping().items()}
            except Exception: self._modemap = {}
        return self._modemap.get(cm, str(cm))

    def _handle(self, msg):
        # 기체(target_system) 가 보낸 메시지만 상태 갱신에 쓴다.
        # 다중 채널 환경에서는 다른 GCS·공격자의 HEARTBEAT 가 라우팅되어 들어오며,
        # 이를 걸러내지 않으면 base_mode=0 을 기체의 시동정지로 오인한다.
        try:
            if msg.get_srcSystem() != self.m.target_system:
                return
        except Exception:
            pass
        t = msg.get_type()
        if t == 'GLOBAL_POSITION_INT':
            self.S['simms'] = msg.time_boot_ms
            self.S['alt'] = msg.relative_alt / 1000.0
        elif t == 'GPS_RAW_INT':
            self.S['fix'], self.S['sats'] = msg.fix_type, msg.satellites_visible
            if msg.fix_type <= 1: self._mark("gnssLost")
        elif t == 'EXTENDED_SYS_STATE':
            prev = self.S['landed']; self.S['landed'] = msg.landed_state
            if (msg.landed_state == 1 and prev != 1 and self.t_land is not None
                    and self.t_disarm is None and self.S['alt'] <= AIR_ALT_MIN):
                self.t_onground = self.S['simms']; self._mark("landed")
        elif t == 'HEARTBEAT':
            now = time.time()
            if self.last_hb is not None:
                self.hb_gap_max = max(self.hb_gap_max, now - self.last_hb)
            self.last_hb = now
            armed = bool(msg.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
            if self.S['armed'] and not armed and self.t_disarm is None:
                self.t_disarm = self.S['simms']
                self.alt_at_disarm = self.S['alt']
                # landed_state 는 disarm 시 ON_GROUND 로 바뀌므로 공중종료 판정에 쓸 수 없다.
                # 시동정지 시점의 상대고도로 판정한다.
                self.terminated_in_air = (self.S['alt'] > AIR_ALT_MIN)
                self._mark("motorsDisarmed")
            self.S['armed'] = armed
            nm = self._modename(msg.custom_mode)
            if nm != self.S['mode']:
                self.S['mode'] = nm
                if nm == 'LAND' and self.t_land is None:
                    self.t_land = self.S['simms']; self._mark("fsLand")
        elif t == 'STATUSTEXT':
            s = msg.text.strip()
            self.events.append(dict(stage='STATUSTEXT', simms=self.S['simms'], detail=s))
            if 'position lost' in s:
                self._mark("ekfPosLost"); self._mark("navBranch")
            if 'over thresholds' in s:
                self._mark("ekfVarExceeded"); self._mark("navBranch")
            if 'Hit ground at' in s:
                try: self.S['impact'] = float(s.split('Hit ground at')[1].split('m/s')[0])
                except Exception: pass

    def _mark(self, pred):
        if pred not in [c[0] for c in self.chain]:
            self.chain.append((pred, self.S['simms']))
            print(f"    [sim {self.S['simms']/1000:8.2f}s] {pred}", flush=True)

    def pump(self, dur):
        e = time.time() + dur
        while time.time() < e:
            msg = self.m.recv_match(blocking=True, timeout=0.2)
            if msg: self._handle(msg)

    # ------------------------------------------------ 기본 동작
    def setp(self, name, val, t=8, critical=True):
        """PARAM_VALUE 로 설정값 일치를 확인한다. 불일치·미수신은 실패."""
        self.m.mav.param_set_send(self.m.target_system, self.m.target_component,
                                  name.encode(), float(val), mav.MAV_PARAM_TYPE_REAL32)
        d = time.time() + t
        while time.time() < d:
            r = self.m.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
            if r and r.param_id.strip('\x00') == name:
                if abs(r.param_value - float(val)) > 1e-6 and critical:
                    self.failures.append(
                        f"파라미터 불일치 {name}: 요청 {val}, 실제 {r.param_value}")
                return r.param_value
        if critical:
            self.failures.append(f"파라미터 미확인 {name} (PARAM_VALUE 미수신)")
        return None

    def _cmd(self, c, *p, wait=2.5):
        p = list(p) + [0]*(7-len(p))
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, c, 0, *p)
        d = time.time() + wait
        while time.time() < d:
            msg = self.m.recv_match(blocking=True, timeout=0.2)
            if not msg: continue
            self._handle(msg)
            if msg.get_type() == 'COMMAND_ACK' and msg.command == c:
                return msg.result
        return None

    def preflight(self):
        self.setp('SIM_SPEEDUP', 5, critical=False)
        for n, v in (('SIM_GPS1_ENABLE', 1), ('SIM_GPS1_JAM', 0), ('SIM_GPS1_FIXTYPE', 3),
                     ('FS_EKF_ACTION', 1), ('EK3_OPTIONS', 0)):
            self.setp(n, v)
        d = time.time() + 90
        while time.time() < d:
            self.pump(0.5)
            if self.S['fix'] >= 3 and self.S['sats'] >= 8: break
        self.chain.clear()

    def takeoff(self, alt):
        self._cmd(mav.MAV_CMD_DO_SET_MODE, 1, 4); self.pump(1)
        d = time.time() + 90; armed = False
        while time.time() < d:
            if self._cmd(mav.MAV_CMD_COMPONENT_ARM_DISARM, 1) == 0:
                armed = True; break
            self.pump(5); self._cmd(mav.MAV_CMD_DO_SET_MODE, 1, 4)
        if not armed:
            self.failures.append("시동 실패"); return
        self.S['armed'] = True
        self.pump(1)
        self._cmd(mav.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, alt)
        d = time.time() + 120
        while time.time() < d:
            self.pump(0.5)
            if self.S['alt'] >= alt - 2: break
        if self.S['alt'] < alt - 2:
            self.failures.append(f"이륙 미달 (alt={self.S['alt']:.1f} m)")
        self.pump(3)
        self.setp('SIM_SPEEDUP', 1, critical=False); self.pump(2)
        self.chain.clear(); self.last_hb = None; self.hb_gap_max = 0.0
        self.t_disarm = None; self.terminated_in_air = None

    # ------------------------------------------------ steps 문법
    def observe(self, spec): self.pump(0.3)

    def wait(self, cond, timeout=60):
        """시간초과는 실패다. 조건이 서지 않으면 판정에서 미재현으로 떨어진다."""
        d = time.time() + timeout
        while time.time() < d:
            self.pump(0.3)
            if cond == 'fsLand' and self.S['mode'] == 'LAND': return True
            if cond == 'injectWindow' and self.t_land is not None: return True
            if cond in [c[0] for c in self.chain]: return True
        self.failures.append(f"wait {cond} 시간초과 ({timeout}s)")
        print(f"    [!] wait {cond} 시간초과 — 실패로 기록", flush=True)
        return False

    def send_mode(self, name, num):
        self.t_cmd = self.S['simms']
        r = self._cmd(mav.MAV_CMD_DO_SET_MODE, 1, num); self.pump(1.5)
        self.acks.append(dict(cmd=f"DO_SET_MODE({name})", ack=RESULT.get(r, str(r)),
                              mode_after=self.S['mode'], sim_ms=self.t_cmd))
        if r == 0: self._mark("cmdAccepted")
        print(f"      DO_SET_MODE({name}) ack={RESULT.get(r,r)} -> {self.S['mode']}", flush=True)

    CMD_ARGS = {400: (0, 21196), 185: (1,)}

    def send_cmd(self, c):
        self.t_cmd = self.S['simms']
        args = self.CMD_ARGS.get(int(c), (1,))
        r = self._cmd(c, *args); self.pump(1.5)
        self.acks.append(dict(cmd=f"CMD_{c}{args}", ack=RESULT.get(r, str(r)),
                              mode_after=self.S['mode'], sim_ms=self.t_cmd))
        if r == 0: self._mark("cmdAccepted")
        print(f"      cmd {c}{args} ack={RESULT.get(r,r)}", flush=True)

    def wait_end(self, timeout=160):
        """비행 종료 = 시동정지 또는 접지 중 먼저 오는 것. 시간초과는 실패."""
        d = time.time() + timeout
        while time.time() < d:
            self.pump(0.5)
            if self.t_disarm is not None or self.t_onground is not None: break
        if self.t_disarm is None and self.t_onground is None:
            self.failures.append(f"비행 종료 미관측 ({timeout}s)")
            return False
        self._mark("flightEnd")
        return True

    # 이전 판 호환
    def wait_ground(self, timeout=160): return self.wait_end(timeout)

    # ------------------------------------------------ 판정
    def report(self):
        ends = [t for t in (self.t_disarm, self.t_onground) if t is not None]
        t_end = min(ends) if ends else None
        w1 = round((t_end - self.t_land)/1000, 2) if (t_end and self.t_land) else None
        v = self.S['impact']

        link_alive = self.hb_gap_max < HB_GAP_MAX
        if not link_alive:
            self.failures.append(f"linkAlive 불성립 (최대 단절 {self.hb_gap_max:.1f}s)")

        if w1 is None:                              outcome = None
        elif w1 > BASELINE_W:                       outcome = "extend"
        elif self.terminated_in_air:                outcome = "destroy"
        elif v is not None and v > IMPACT_DESTROY:  outcome = "destroy"
        else:                                       outcome = "recover"

        # 수신 순서가 아니라 시뮬레이션 시각으로 정렬한다. HEARTBEAT 는 고빈도 스트림이고
        # STATUSTEXT 는 이벤트성이라 도착 순서가 인과 순서와 다를 수 있다.
        ev = sorted([(t, p) for p, t in self.chain if p in EXPECTED_CHAIN])
        seq = [p for _, p in ev]
        present = all(p in seq for p in EXPECTED_CHAIN)
        tmap = {p: t for t, p in ev}
        ordered = present and all(
            tmap[a] <= tmap[b] + ORDER_TOL_MS
            for a, b in zip(EXPECTED_CHAIN, EXPECTED_CHAIN[1:]))
        reproduced = present and ordered and link_alive and not self.failures

        here0 = os.path.dirname(os.path.abspath(__file__))
        def _sha(f):
            p = os.path.join(here0, f)
            return hashlib.sha256(open(p,'rb').read()).hexdigest()[:12] if os.path.exists(p) else None
        try:
            commit = subprocess.run(["git","-C",_AP,"rev-parse","--short","HEAD"],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            commit = None
        meta = dict(run_at=datetime.datetime.now().isoformat(timespec="seconds"),
                    ardupilot_commit=commit, model="claude-sonnet-5",
                    graph_sha=_sha("graph.py"), gates_sha=_sha("gates.py"),
                    runtime_sha=_sha("runtime.py"),
                    script_sha=_sha(os.path.join("scripts", self.sid + ".py")))
        out = dict(id=self.sid, branch=self.branch, meta=meta,
                   chain=self.chain, chain_seq=seq,
                   chain_present=present, chain_ordered=ordered,
                   link_alive=link_alive, hb_gap_max_s=round(self.hb_gap_max, 2),
                   acks=self.acks,
                   t_land_ms=self.t_land, t_disarm_ms=self.t_disarm,
                   t_onground_ms=self.t_onground,
                   terminated_in_air=self.terminated_in_air,
                   window_s=w1, impact_mps=v, alt_at_disarm=self.alt_at_disarm,
                   outcome=outcome, expected_outcome=self.expected,
                   outcome_match=(outcome == self.expected),
                   chain_reproduced=reproduced,
                   failures=self.failures, ok=(not self.failures),
                   events=self.events, tlog=self.tlog_path)
        here = os.path.dirname(os.path.abspath(__file__))
        os.makedirs(os.path.join(here, "runs"), exist_ok=True)
        json.dump(out, open(os.path.join(here, "runs", f"{self.sid}.json"), "w"),
                  ensure_ascii=False, indent=1)
        st = "재현" if reproduced else "미재현"
        print(f"\n[=] {self.sid} [{self.branch}]  창 {w1} s | 접지 {v} | "
              f"공중종료 {self.terminated_in_air} | 판정 {outcome} (기대 {self.expected}) | "
              f"사슬 {st} (순서 {ordered}, linkAlive {link_alive})", flush=True)
        for f in self.failures:
            print(f"    [!] {f}", flush=True)
