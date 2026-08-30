# -*- coding: utf-8 -*-
"""경로를 언어모델로 시나리오로 전개하고 세 게이트를 적용한다.

언어모델의 자리는 전개뿐이다. 공격의 성립 여부는 그래프가 정하고
생성물의 적합 여부는 게이트가 정한다.

usage: python3 generate.py [--n N] [--model MODEL]
"""
import json, re, subprocess, sys, argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph import (enumerate_paths, path_string, OBSERVED, DERIVED,
                   POS_INDEPENDENT, INJECTION, BASELINE_WINDOW)
from gates import run_gates

MODEL = "claude-sonnet-5"

PROMPT = """다음은 무인기 대상 혼합 공격그래프에서 열거된 경로 하나다.
이 경로를 ArduPilot SITL에서 실행 가능한 모의침투 시나리오로 전개하라.

[경로]
{path}
분기 교란 수단: {injection}
주입 명령: {command}

[사용 가능한 술어 — 이 목록 밖의 술어를 쓰면 폐기된다]
관측 술어: {observed}
유도 술어: {derived}

[steps 문법 — 이 네 형태만 허용된다]
  set <PARAM>=<VALUE>       PARAM in {params}
  observe <MSG>[.<field>]   MSG in {msgs}
  send <MAV_CMD_...>        posIndependent 집합의 명령만
  wait <조건>

[출력 형식 — JSON 객체 하나만. 설명 문장 금지]
{{
  "id": "...",
  "path": "...",
  "precondition": ["..."],
  "steps": ["set ...", "observe ...", "send ..."],
  "observable": ["MSG.field", ...],
  "success": "술어로 표현한 성공 판정",
  "abort": ["...", "..."]
}}

주의: 명령 주입의 창은 대조군에서 {w0}초로 측정되었다. steps는 이 창 안에서 끝나야 한다.
"""


def build_prompt(p):
    return PROMPT.format(
        path=path_string(p), injection=p["injection"], command=p["command"],
        observed=", ".join(sorted(OBSERVED)), derived=", ".join(sorted(DERIVED)),
        params="{SIM_GPS1_ENABLE, SIM_GPS1_JAM, FS_EKF_ACTION, EK3_OPTIONS}",
        msgs="{GPS_RAW_INT, STATUSTEXT, HEARTBEAT, COMMAND_ACK, GLOBAL_POSITION_INT}",
        w0=BASELINE_WINDOW)


def call_llm(prompt, model=MODEL, timeout=180):
    r = subprocess.run(["claude", "-p", prompt, "--model", model],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def extract_json(text):
    """생성물에서 JSON 객체를 뽑는다. 실패하면 None."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        i, j = text.find("{"), text.rfind("}")
        raw = text[i:j+1] if i >= 0 and j > i else None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()

    paths = enumerate_paths()[:a.n]
    print(f"경로 {len(paths)}개, 모델 {a.model}\n")
    results = []
    for p in paths:
        out = call_llm(build_prompt(p), a.model)
        sc = extract_json(out)
        if sc is None:
            rec = dict(path_id=p["id"], gates_passed=0,
                       reasons=["[G1 스키마] JSON 파싱 실패"], scenario=None)
        else:
            sc.setdefault("id", p["id"])
            passed, reasons = run_gates(sc)
            rec = dict(path_id=p["id"], gates_passed=passed,
                       reasons=reasons, scenario=sc)
        rec["expected_outcome"] = p["expected_outcome"]
        rec["command"] = p["command"]
        rec["branch"] = p["branch"].split("(")[1].rstrip(")")
        rec["injection"] = p["injection"]
        results.append(rec)
        mark = "통과" if rec["gates_passed"] == 3 else f"{rec['gates_passed']}/3"
        print(f"  {p['id']}  {p['command']:35} 게이트 {mark}")
        for r in rec["reasons"][:2]:
            print(f"           {r}")

    ok = sum(1 for r in results if r["gates_passed"] == 3)
    print(f"\n게이트 통과 {ok}/{len(results)} ({ok/len(results)*100:.0f}%)")
    json.dump(results, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
              "generated.json"), "w"), ensure_ascii=False, indent=1)
    print("[+] generated.json 기록")


if __name__ == "__main__":
    main()
