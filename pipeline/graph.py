# -*- coding: utf-8 -*-
"""혼합 공격그래프의 정의와 경로 열거.

조건 어휘는 게이트 2가 참조하는 유일한 출처이며, 원고 3.1~3.2의 정의와
같은 이름을 쓴다. 런타임이 실제로 표시하는 조건은 RUNTIME 에 모아 두었고
게이트 3의 wait 검사가 이 집합을 참조한다.
"""

# ---------------------------------------------------------------- 조건 어휘
# 관측 조건 : MAVLink 메시지에서 직접 채워진다 (원고 Table 2)
OBSERVED = {
    "gnssLost":       ("GPS_RAW_INT",  "fix_type <= 1"),
    "navBranch":      ("STATUSTEXT",   "over thresholds 또는 position lost"),
    "fsLand":         ("HEARTBEAT",    "custom_mode = LAND"),
    "motorsDisarmed": ("HEARTBEAT",    "base_mode 의 SAFETY_ARMED 1 -> 0"),
    "landed":         ("EXTENDED_SYS_STATE", "landed_state = ON_GROUND"),
    "alt":            ("GLOBAL_POSITION_INT", "relative_alt"),
    "linkAlive":      ("HEARTBEAT",    "단절이 3.0초 미만"),
    "modeChanged":    ("HEARTBEAT",    "custom_mode 가 주입값으로 변경"),
    "cmdAccepted":    ("COMMAND_ACK",  "result = MAV_RESULT_ACCEPTED"),
}
# 상태전이 조건 : 규칙으로 얻는다 (원고 Table 3)
DERIVED = {
    "flightEnd", "controlEffectWindow", "injectWindow",
    "attemptInject", "injectSucceeded",
}
# 구성 사실과 정적 라벨
CONFIG = {"reachable", "noSigning"}
LABEL  = {"posIndependent"}
VOCAB = set(OBSERVED) | DERIVED | CONFIG | LABEL

# 런타임이 실제로 표시하는 조건. 게이트 3 의 wait 검사가 이 집합으로 제한된다.
RUNTIME = {"gnssLost", "navBranch", "ekfVarExceeded", "ekfPosLost",
           "fsLand", "injectWindow", "modeChanged", "injectSucceeded",
           "motorsDisarmed", "landed", "flightEnd", "cmdAccepted"}

# ---------------------------------------------------------------- 노드
NODES = {
    "EX-0016.03":   dict(type="technique", label="SPARTA PNT Jamming",
                         evidence="SPARTA EX-0016.03"),
    "gnssArtifact": dict(type="artifact",  label="GNSS 신호 상실/품질 저하",
                         evidence="D3FEND GNSSSignal"),
    "navBranch(variance)": dict(type="observed", label="EKF 분산 임계 초과",
                         evidence="ArduPilot ekf_check.cpp"),
    "navBranch(posLost)":  dict(type="observed", label="위치 추정 상실",
                         evidence="ArduPilot ekf_check.cpp"),
    "fsLand":       dict(type="fcs",       label="EKF failsafe -> LAND",
                         evidence="log: mode transition"),
    "injectWindow": dict(type="opportunity", label="명령 주입 창 w",
                         evidence="log: tg - tm"),
    "attemptInject": dict(type="cyber",    label="미서명 명령 주입 시도",
                         evidence="실행 전 열거"),
    "injectSucceeded": dict(type="post",   label="모드 변경 관측",
                         evidence="log: HEARTBEAT.custom_mode"),
}

# ---------------------------------------------------------------- 간선
EDGES = [
    ("EX-0016.03",   "gnssArtifact",          "ewEffect"),
    ("gnssArtifact", "navBranch(variance)",   "stateTransition"),
    ("gnssArtifact", "navBranch(posLost)",    "stateTransition"),
    ("navBranch(variance)", "fsLand",         "stateTransition"),
    ("navBranch(posLost)",  "fsLand",         "stateTransition"),
    ("fsLand",       "injectWindow",          "stateTransition"),
    ("injectWindow", "attemptInject",         "exploit"),
    ("attemptInject", "injectSucceeded",      "stateTransition"),
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
    "navBranch(posLost)":  "SIM_GPS1_ENABLE=0",
    "navBranch(variance)": "SIM_GPS1_JAM=1",
}


def enumerate_paths():
    """그래프에서 도달 가능한 구체 경로를 열거한다.

    분기 2종 x posIndependent 명령 5종 = 10개. 위치 의존 명령은
    attemptInject 의 전제조건 posIndependent(c) 를 만족하지 못하므로 열거되지 않는다.
    """
    out = []
    for branch in ("navBranch(posLost)", "navBranch(variance)"):
        for cmd, meta in POS_INDEPENDENT.items():
            out.append(dict(
                id=f"SC-{len(out)+1:02d}",
                nodes=["EX-0016.03", "gnssArtifact", branch, "fsLand",
                       "injectWindow", "attemptInject", "injectSucceeded"],
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
