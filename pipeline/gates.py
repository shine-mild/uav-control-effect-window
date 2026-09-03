# -*- coding: utf-8 -*-
"""시나리오 생성물의 세 검증 게이트.

G1 스키마 적합성   — 일곱 필수 항목의 존재와 자료형
G2 조건 어휘 적합성 — path/success 의 기호가 정의된 조건 집합에 속하는가
G3 실행 가능성     — steps 의 각 항목이 MAVLink 명령·파라미터로 변환되는가.
                    wait 의 대상은 런타임이 실제로 표시하는 조건이어야 한다.

게이트의 목적은 생성물을 정성 평가하지 않는 것이다. 통과/불통과와 사유만 남긴다.
"""
import re
from graph import VOCAB, RUNTIME, POS_INDEPENDENT, POS_DEPENDENT

REQUIRED = {
    "id": str, "path": str, "precondition": list, "steps": list,
    "observable": list, "success": str, "abort": list,
}
# 실행 스크립트로 변환 가능한 단계 문법
STEP_SET     = re.compile(r"^set\s+([A-Z0-9_]+)\s*=\s*(-?[\d.]+)$")
STEP_OBSERVE = re.compile(r"^observe\s+([A-Z_]+(?:\.[A-Za-z_]+)?(?:\s*,\s*[A-Z_]+(?:\.[A-Za-z_]+)?)*)$")
STEP_SEND    = re.compile(r"^send\s+(MAV_CMD_[A-Z_]+(?:\([A-Z_0-9]+\))?)$")
STEP_WAIT    = re.compile(r"^wait\s+(\w+)(?:\s*=\s*(\w+))?$")

KNOWN_MSGS = {"GPS_RAW_INT", "STATUSTEXT", "HEARTBEAT", "COMMAND_ACK",
              "GLOBAL_POSITION_INT", "EKF_STATUS_REPORT", "SYS_STATUS"}
KNOWN_PARAMS = {"SIM_GPS1_ENABLE", "SIM_GPS1_JAM", "SIM_GPS1_FIXTYPE",
                "FS_EKF_ACTION", "EK3_OPTIONS", "SIM_SPEEDUP"}


def gate1_schema(sc):
    """필수 항목의 존재와 자료형."""
    bad = []
    if not isinstance(sc, dict):
        return False, ["최상위가 객체가 아님"]
    for k, t in REQUIRED.items():
        if k not in sc:
            bad.append(f"항목 누락: {k}")
        elif not isinstance(sc[k], t):
            bad.append(f"자료형 불일치: {k} (기대 {t.__name__}, 실제 {type(sc[k]).__name__})")
    if isinstance(sc.get("steps"), list) and not sc["steps"]:
        bad.append("steps 가 비어 있음")
    return (not bad), bad


def gate2_vocabulary(sc):
    """path 와 success 의 기호가 정의된 조건 어휘에 속하는가."""
    bad = []
    text = f"{sc.get('path','')} {sc.get('success','')}"
    # 식별자 형태의 토큰만 검사. 노드 id 와 MAVLink 상수는 어휘 밖이므로 제외한다.
    for tok in set(re.findall(r"\b([a-z][A-Za-z]+)\s*\(", text)):
        if tok not in VOCAB:
            bad.append(f"정의되지 않은 조건: {tok}")
    # 위치 의존 명령을 쓰면 attemptInject 의 전제조건이 성립하지 않는다.
    # 모드 이름은 괄호로 둘러싸인 형태로만 비교한다. 부분 문자열로 비교하면
    # GUIDED 가 GUIDED_NOGPS 를 잘못 잡는다.
    for c in POS_DEPENDENT:
        mode = c.split("(")[1].rstrip(")") if "(" in c else None
        if c in text or (mode and re.search(rf"\(\s*{mode}\s*\)", text)):
            bad.append(f"posIndependent 불성립 명령 사용: {c}")
    return (not bad), bad


def gate3_executable(sc):
    """steps 의 각 항목이 실행 가능한 형태인가."""
    bad = []
    for i, st in enumerate(sc.get("steps", []), 1):
        if not isinstance(st, str):
            bad.append(f"{i}행: 문자열이 아님"); continue
        s = re.sub(r"^t\d+\s+|^t\?\s+", "", st.strip())
        if m := STEP_SET.match(s):
            if m.group(1) not in KNOWN_PARAMS:
                bad.append(f"{i}행: 알 수 없는 파라미터 {m.group(1)}")
        elif m := STEP_OBSERVE.match(s):
            for f in re.split(r"\s*,\s*", m.group(1)):
                if f.split(".")[0] not in KNOWN_MSGS:
                    bad.append(f"{i}행: 알 수 없는 메시지 {f}")
        elif m := STEP_SEND.match(s):
            c = m.group(1)
            if c not in POS_INDEPENDENT:
                # 인자를 요구하는 명령을 인자 없이 쓰면 스크립트로 변환되지 않는다
                if c in {k.split("(")[0] for k in POS_INDEPENDENT if "(" in k}:
                    bad.append(f"{i}행: {c} 에 모드 인자가 없어 변환 불가")
                else:
                    bad.append(f"{i}행: posIndependent 집합 밖의 명령 {c}")
        elif m := STEP_WAIT.match(s):
            # 런타임이 표시하지 않는 조건을 기다리면 실행이 시간초과로 끝난다.
            # 임의의 단어를 통과시키지 않는다.
            if m.group(1) not in RUNTIME:
                bad.append(f"{i}행: 런타임이 표시하지 않는 대기 조건 {m.group(1)}")
        else:
            bad.append(f"{i}행: 변환 불가한 문법 — {st!r}")
    return (not bad), bad


GATES = [("G1 스키마", gate1_schema),
         ("G2 조건어휘", gate2_vocabulary),
         ("G3 실행가능", gate3_executable)]


def run_gates(sc):
    """세 게이트를 순서대로 적용. 통과 개수와 사유를 반환한다."""
    passed, reasons = 0, []
    for name, fn in GATES:
        ok, bad = fn(sc)
        if ok:
            passed += 1
        else:
            reasons += [f"[{name}] {b}" for b in bad]
            break          # 앞 게이트에서 걸리면 뒤는 판정하지 않는다
    return passed, reasons
