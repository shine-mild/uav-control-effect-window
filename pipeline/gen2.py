# -*- coding: utf-8 -*-
"""2차 생성 표본 — 프롬프트·모델·게이트를 바꾸지 않고 독립 생성만 다시 한다.

1차 표본은 개발집합이다. 같은 생성물을 보고 변환기를 고쳤기 때문이다.
2차 표본은 그 뒤 고정된 게이트·변환기로 처음 평가하는 표본이다.

호출 간격을 두고, 원시 출력을 모두 남긴다. 빈 응답(전송 실패)과
형식이 어긋난 생성물(모델 실패)을 구분해서 세기 위해서다.
"""
import json, os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G
from gates import run_gates

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen2_raw")
os.makedirs(OUT, exist_ok=True)
GAP = float(os.environ.get("GEN_GAP", "20"))

res = []
for p in G.enumerate_paths()[:10]:
    attempts, sc, raw = [], None, ""
    for k in range(2):                      # 전송 실패만 한 번 더 시도한다
        r = subprocess.run(["claude", "-p", G.build_prompt(p), "--model", G.MODEL],
                           capture_output=True, text=True, timeout=300)
        raw = r.stdout.strip()
        open(os.path.join(OUT, f"{p['id']}-{k}.txt"), "w", encoding="utf-8").write(raw)
        attempts.append(dict(rc=r.returncode, bytes=len(raw)))
        sc = G.extract_json(raw)
        if raw:                             # 응답이 있으면 그것으로 판정한다
            break
        time.sleep(GAP)
    if sc is None:
        rec = dict(path_id=p["id"], gates_passed=0, scenario=None,
                   reasons=["[G1 스키마] JSON 파싱 실패"] if raw else ["전송 실패(빈 응답)"],
                   empty_response=(raw == ""))
    else:
        sc.setdefault("id", p["id"])
        passed, reasons = run_gates(sc)
        rec = dict(path_id=p["id"], gates_passed=passed, reasons=reasons,
                   scenario=sc, empty_response=False)
    rec.update(attempts=attempts, command=p["command"], branch=p["branch"].split("(")[1].rstrip(")"))
    res.append(rec)
    print(f"  {p['id']}  {p['command']:35} {rec['gates_passed']}/3 "
          f"{'빈응답' if rec['empty_response'] else ''}", flush=True)
    time.sleep(GAP)

ok = sum(1 for r in res if r["gates_passed"] == 3)
empty = sum(1 for r in res if r["empty_response"])
print(f"\n2차 표본 게이트 3/3 통과 {ok}/10 · 빈 응답 {empty}건")
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
          "..", "data", "generated_v2.json"), "w"), ensure_ascii=False, indent=1)
print("[+] data/generated_v2.json 기록")
