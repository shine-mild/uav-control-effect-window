# -*- coding: utf-8 -*-
"""L 조건 — 언어모델 생성. 프롬프트에서 고정 시간창 지시만 뺀 판본.

원본 pipeline/generate.py 와 다른 점은 PROMPT 마지막 줄 하나뿐이다.
게이트·변환·실행기는 그대로 쓴다.
"""
import json, os, re, subprocess, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph import (enumerate_paths, path_string, OBSERVED, DERIVED, RUNTIME, CONFIG, LABEL)
from gates import run_gates

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-sonnet-5"

# 원본과 동일. 마지막 "주의" 줄만 교체한다.
PROMPT = """다음은 무인기 대상 혼합 공격그래프에서 열거된 경로 하나다.
이 경로를 ArduPilot SITL에서 실행 가능한 모의침투 시나리오로 전개하라.

[경로]
{path}
분기 교란 수단: {injection}
주입 명령: {command}

[사용 가능한 조건 — 이 목록 밖의 이름을 쓰면 폐기된다]
관측 조건: {observed}
상태전이 조건: {derived}
구성 사실·정적 라벨: {config}

[steps 문법 — 이 네 형태만 허용된다]
  set <PARAM>=<VALUE>       PARAM in {params}
  observe <MSG>[.<field>]   MSG in {msgs}
  send <MAV_CMD_...>        위의 [주입 명령] 을 괄호까지 그대로 적을 것.
                           예: send MAV_CMD_DO_SET_MODE(ALT_HOLD)
                           모드 인자를 빠뜨리면 변환되지 않아 폐기된다.
  wait <조건>            조건 in {runtime}  (이 목록 밖은 폐기된다)

[출력 형식 — JSON 객체 하나만. 코드블록과 설명 문장 없이 여는 중괄호로 시작해 닫는 중괄호로 끝낼 것]
{{
  "id": "...",
  "path": "...",
  "precondition": ["..."],
  "steps": ["set ...", "observe ...", "send ..."],
  "observable": ["MSG.field", ...],
  "success": "조건으로 표현한 성공 판정",
  "abort": ["...", "..."]
}}

주의: 종료까지의 시간은 명령과 조종 입력에 따라 달라지므로 고정된 상한을 가정하지 말 것.
steps 는 마지막 관측 조건까지 적고, 관측 상한은 실행기가 정한다.
"""


def build_prompt(p):
    return PROMPT.format(
        path=path_string(p), injection=p["injection"], command=p["command"],
        observed=", ".join(sorted(OBSERVED)), derived=", ".join(sorted(DERIVED)),
        config=", ".join(sorted(CONFIG | LABEL)),
        runtime="{" + ", ".join(sorted(RUNTIME)) + "}",
        params="{SIM_GPS1_ENABLE, SIM_GPS1_JAM, FS_EKF_ACTION, EK3_OPTIONS}",
        msgs="{GPS_RAW_INT, STATUSTEXT, HEARTBEAT, COMMAND_ACK, GLOBAL_POSITION_INT}")


def extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        i, j = text.find("{"), text.rfind("}")
        raw = text[i:j+1] if i >= 0 and j > i else None
    if raw is None: return None
    try: return json.loads(raw)
    except json.JSONDecodeError: return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--gap", type=float, default=20.0)
    a = ap.parse_args()
    os.makedirs(os.path.join(HERE, "raw"), exist_ok=True)
    res = []
    for k, p in enumerate(enumerate_paths()):
        if k: time.sleep(a.gap)          # 연속 호출의 전송 실패를 피한다
        pr = build_prompt(p)
        try:
            r = subprocess.run(["claude", "-p", pr, "--model", MODEL],
                               capture_output=True, text=True, timeout=240)
            out = r.stdout.strip()
        except subprocess.TimeoutExpired:
            out = ""
        open(os.path.join(HERE, "raw", f"L-{p['id']}.txt"), "w", encoding="utf-8").write(out)
        sc = extract_json(out)
        if sc is None:
            rec = dict(path_id=p["id"], gates_passed=0, reasons=["[G1 스키마] JSON 파싱 실패"], scenario=None)
        else:
            sc.setdefault("id", p["id"])
            passed, reasons = run_gates(sc)
            rec = dict(path_id=p["id"], gates_passed=passed, reasons=reasons, scenario=sc)
        rec.update(expected_outcome=p["expected_outcome"], command=p["command"],
                   branch=p["branch"].split("(")[1].rstrip(")"), injection=p["injection"])
        res.append(rec)
        print(f"  {p['id']}  {p['command']:36} 검사 {rec['gates_passed']}/3  "
              + ("" if rec['gates_passed']==3 else str(rec['reasons'][:1])), flush=True)
    ok = sum(1 for r in res if r["gates_passed"] == 3)
    json.dump(res, open(os.path.join(HERE, "generated_L.json"), "w"), ensure_ascii=False, indent=1)
    print(f"\nL 조건 정적 검사 통과 {ok}/{len(res)}")


if __name__ == "__main__":
    main()
