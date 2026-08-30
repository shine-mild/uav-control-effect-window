# -*- coding: utf-8 -*-
"""혼합 공격그래프의 정의와 경로 열거.

노드 5타입 / 간선 3타입. 술어 어휘는 게이트 2가 참조하는 유일한 출처다.
"""

# ---------------------------------------------------------------- 술어 어휘
# 관측 술어 : MAVLink 메시지에서 직접 채워진다
OBSERVED = {
    "gnssLost":       ("GPS_RAW_INT",  "fix_type <= 1"),
    "ekfVarExceeded": ("STATUSTEXT",   "EKF variance: over thresholds"),
    "ekfPosLost":     ("STATUSTEXT",   "EKF variance: position lost"),
    "mode":           ("HEARTBEAT",    "custom_mode"),
    "grounded":       ("HEARTBEAT",    "armed = 0"),
    "linkAlive":      ("HEARTBEAT",    "수신 간격 내 단절 없음"),
    "cmdAccepted":    ("COMMAND_ACK",  "result = MAV_RESULT_ACCEPTED"),
    "impactSpeed":    ("STATUSTEXT",   "SIM Hit ground at N m/s"),
}
# 유도 술어 : 규칙으로 얻는다
DERIVED = {
    "navDegraded", "fsLand", "descentWindow", "injectWindow",
    "cmdInject", "effect", "outcome", "posIndependent", "noSigning",
}
VOCAB = set(OBSERVED) | DERIVED

# ---------------------------------------------------------------- 노드
NODES = {
    "EX-0016.03":   dict(type="technique", label="SPARTA PNT Jamming",
                         evidence="SPARTA EX-0016.03"),
    "gnssArtifact": dict(type="artifact",  label="GNSS 신호 상실/품질 저하",
                         evidence="D3FEND GNSSSignal"),
    "navDegraded(variance)": dict(type="observed", label="EKF 분산 임계 초과",
                         evidence="ArduPilot ekf_check.cpp"),
    "navDegraded(posLost)":  dict(type="observed", label="위치 추정 상실",
                         evidence="ArduPilot ekf_check.cpp"),
    "fsLand":       dict(type="fcs",       label="EKF failsafe -> LAND",
                         evidence="log: mode transition"),
    "injectWindow": dict(type="opportunity", label="명령 주입 창 w",
                         evidence="log: tg - tm"),
    "cmdInject":    dict(type="cyber",     label="MAVLink 명령 주입",
                         evidence="log: COMMAND_ACK"),
    "effect":       dict(type="post",      label="사후 상태 (w1, v)",
                         evidence="log: window + impact"),
}

# ---------------------------------------------------------------- 간선
EDGES = [
    ("EX-0016.03",   "gnssArtifact",          "ewEffect"),
    ("gnssArtifact", "navDegraded(variance)", "stateTransition"),
    ("gnssArtifact", "navDegraded(posLost)",  "stateTransition"),
    ("navDegraded(variance)", "fsLand",       "stateTransition"),
    ("navDegraded(posLost)",  "fsLand",       "stateTransition"),
    ("fsLand",       "injectWindow",          "stateTransition"),
    ("injectWindow", "cmdInject",             "exploit"),
    ("cmdInject",    "effect",                "stateTransition"),
]

# ---------------------------------------------------------------- 관측으로 채워진 집합
# 2026-08-25 예비실험 13회에서 판정. 문헌이 아니라 측정이 출처다.
POS_INDEPENDENT = {
    "MAV_CMD_DO_SET_MODE(STABILIZE)":    dict(outcome="destroy", w=17.15, v=16.20),
    "MAV_CMD_DO_SET_MODE(ALT_HOLD)":     dict(outcome="recover", w=31.05, v=2.50),
    "MAV_CMD_DO_SET_MODE(GUIDED_NOGPS)": dict(outcome="extend",  w=92.85, v=None),
    "MAV_CMD_DO_FLIGHTTERMINATION":      dict(outcome="destroy", w=3.15,  v=None),
    "MAV_CMD_COMPONENT_ARM_DISARM":      dict(outcome="destroy", w=3.15,  v=None),
}
POS_DEPENDENT = {
    "MAV_CMD_DO_SET_MODE(LOITER)", "MAV_CMD_DO_SET_MODE(GUIDED)",
    "MAV_CMD_DO_SET_MODE(RTL)", "MAV_CMD_DO_SET_MODE(AUTO)",
    "MAV_CMD_DO_SET_MODE(POSHOLD)", "MAV_CMD_DO_SET_MODE(BRAKE)",
    "MAV_CMD_DO_SET_MODE(SMART_RTL)",
}
BASELINE_WINDOW = 48.35   # w0
BASELINE_IMPACT = 0.50    # v0

# 교란 주입 수단 (분기별)
INJECTION = {
    "navDegraded(posLost)":  "SIM_GPS1_ENABLE=0",
    "navDegraded(variance)": "SIM_GPS1_JAM=1",
}


def enumerate_paths():
    """그래프에서 도달 가능한 구체 경로를 열거한다.

    분기 2종 x posIndependent 명령 5종 = 10개. 위치 의존 명령은
    cmdInject 의 전제조건 posIndependent(c) 를 만족하지 못하므로 열거되지 않는다.
    """
    out = []
    for branch in ("navDegraded(posLost)", "navDegraded(variance)"):
        for cmd, meta in POS_INDEPENDENT.items():
            out.append(dict(
                id=f"SC-{len(out)+1:02d}",
                nodes=["EX-0016.03", "gnssArtifact", branch, "fsLand",
                       "injectWindow", "cmdInject", "effect"],
                branch=branch,
                injection=INJECTION[branch],
                command=cmd,
                expected_outcome=meta["outcome"],
            ))
    return out


def path_string(p):
    return " -> ".join(p["nodes"])


if __name__ == "__main__":
    ps = enumerate_paths()
    print(f"노드 {len(NODES)}개(5타입), 간선 {len(EDGES)}개(3타입), 술어 어휘 {len(VOCAB)}종")
    print(f"열거된 경로 {len(ps)}개 "
          f"(분기 2 x posIndependent {len(POS_INDEPENDENT)})")
    print(f"제외된 위치 의존 명령 {len(POS_DEPENDENT)}종 — "
          f"전제조건 posIndependent(c) 불성립\n")
    for p in ps[:3]:
        print(f"  {p['id']}  {p['branch']:24} {p['command']:35} -> {p['expected_outcome']}")
    print("  ...")
