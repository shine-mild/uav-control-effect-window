# -*- coding: utf-8 -*-
"""P6 대조군 — 결정론적 템플릿(T) 생성기와 T/L/P 비교.

T : 그래프 경로를 고정 템플릿으로 채워 시나리오를 만든다. 언어모델을 쓰지 않는다.
L : 언어모델 생성물, 게이트 적용 전
P : 언어모델 생성물 + 세 게이트

L 은 실행하지 않고 오프라인 판정만 한다. 변환 불가하거나 전제조건을 어긴 생성물을
실행하지 않는 것이 설계 의도이기 때문이다.
"""
import json, os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph import enumerate_paths, path_string, INJECTION, POS_INDEPENDENT, VOCAB
from gates import run_gates, gate1_schema, gate2_vocabulary, gate3_executable

HERE = os.path.dirname(os.path.abspath(__file__))


def template_scenario(p):
    """경로 -> 시나리오. 그래프가 가진 정보만으로 결정론적으로 채운다."""
    branch = p["branch"].split("(")[1].rstrip(")")
    param, val = p["injection"].split("=")
    wait_pred = "ekfPosLost" if branch == "posLost" else "ekfVarExceeded"
    cmd = p["command"]
    return {
        "id": p["id"],
        "path": path_string(p),
        "precondition": ["noSigning", "linkAlive", f"navBranch({branch})"],
        "steps": [f"set {param}={val}",
                  "observe GPS_RAW_INT",
                  f"wait {wait_pred}",
                  "wait fsLand",
                  f"send {cmd}",
                  "observe COMMAND_ACK"],
        "observable": ["GPS_RAW_INT.fix_type", "STATUSTEXT",
                       "HEARTBEAT.custom_mode", "COMMAND_ACK.result"],
        "success": "cmdAccepted(U, c)",
        "abort": ["고도 1 m 미만", "시뮬레이션 시각 300 s 초과"],
    }


def precondition_ok(sc, p):
    """전제조건 준수: 주입 수단이 경로의 분기와 일치하고 명령이 posIndependent 인가."""
    steps = " ".join(sc.get("steps", []) if isinstance(sc.get("steps"), list) else [])
    inj_ok = p["injection"].replace(" ", "") in steps.replace(" ", "")
    cmd_ok = any(c in steps for c in POS_INDEPENDENT)
    return inj_ok and cmd_ok


def uniq_ok(scs):
    ids = [s.get("id") for s in scs if s]
    return len(set(ids)) == len(ids)


def evaluate(name, scenarios, paths):
    """스키마·어휘·변환·전제조건 네 지표를 센다."""
    n = len(paths)
    g1 = g2 = g3 = pre = 0
    for sc, p in zip(scenarios, paths):
        if sc is None: continue
        if gate1_schema(sc)[0]: g1 += 1
        if gate2_vocabulary(sc)[0]: g2 += 1
        if gate3_executable(sc)[0]: g3 += 1
        if precondition_ok(sc, p): pre += 1
    uniq = uniq_ok(scenarios)
    return dict(method=name, n=n, schema=g1, vocab=g2, executable=g3,
                precondition=pre, unique_ids=uniq)


def main():
    paths = enumerate_paths()
    gen = json.load(open(os.path.join(HERE, "generated.json"), encoding="utf-8"))
    llm = [r["scenario"] for r in gen]

    T = [template_scenario(p) for p in paths]
    rows = [evaluate("T 템플릿", T, paths),
            evaluate("L 언어모델(게이트 전)", llm, paths)]
    # P 는 L 중 세 게이트를 모두 통과한 것만 남긴 집합
    passed = [(r["scenario"] if r["gates_passed"] == 3 else None) for r in gen]
    rows.append(evaluate("P 언어모델+게이트", passed, paths))

    hdr = f"{'방식':<22}{'n':>3}{'스키마':>7}{'어휘':>6}{'변환가능':>9}{'전제준수':>9}{'ID고유':>8}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['method']:<22}{r['n']:>3}{r['schema']:>7}{r['vocab']:>6}"
              f"{r['executable']:>9}{r['precondition']:>9}{str(r['unique_ids']):>8}")

    # 생성 다양성 : 서로 다른 steps 시퀀스의 개수
    def diversity(scs):
        sigs = {tuple(s.get("steps", [])) for s in scs if s}
        return len(sigs)
    print(f"\n생성 다양성 (서로 다른 steps 시퀀스)  T {diversity(T)} / L {diversity(llm)}")

    json.dump(rows, open(os.path.join(HERE, "compare_TLP.json"), "w"),
              ensure_ascii=False, indent=1)
    # 템플릿 시나리오도 보존
    json.dump([dict(path_id=p["id"], branch=p["branch"].split("(")[1].rstrip(")"),
                    expected_outcome=p["expected_outcome"], command=p["command"],
                    gates_passed=sum(run_gates(t)[0:1]), scenario=t)
               for t, p in zip(T, paths)],
              open(os.path.join(HERE, "generated_template.json"), "w"),
              ensure_ascii=False, indent=1)
    print("[+] compare_TLP.json, generated_template.json 기록")


if __name__ == "__main__":
    main()
