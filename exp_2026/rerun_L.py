# -*- coding: utf-8 -*-
"""전송 실패(사용량 한도)로 비어 있던 경로만 다시 생성한다. 프롬프트·게이트는 그대로."""
import json, os, sys, subprocess, time, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "gen_L.py"))
g = importlib.util.module_from_spec(spec)
sys.argv = ["x"]
import runpy
# gen_L 의 함수만 쓰기 위해 main 실행을 막고 로드
src = open(os.path.join(HERE, "gen_L.py"), encoding="utf-8").read().replace('if __name__ == "__main__":\n    main()', '')
ns = {"__file__": os.path.join(HERE, "gen_L.py"), "__name__": "genL"}
exec(compile(src, "gen_L.py", "exec"), ns)
from graph import enumerate_paths
from gates import run_gates

res = json.load(open(os.path.join(HERE, "generated_L.json"), encoding="utf-8"))
paths = {p["id"]: p for p in enumerate_paths()}
todo = [r for r in res if r["gates_passed"] != 3 and r["scenario"] is None]
print("다시 생성할 경로:", [r["path_id"] for r in todo])
for k, r in enumerate(todo):
    if k: time.sleep(25)
    p = paths[r["path_id"]]
    out = subprocess.run(["claude", "-p", ns["build_prompt"](p), "--model", "claude-sonnet-5"],
                         capture_output=True, text=True, timeout=240).stdout.strip()
    open(os.path.join(HERE, "raw", f"L-{p['id']}.txt"), "w", encoding="utf-8").write(out)
    if "session limit" in out.lower() or not out:
        print(f"  {p['id']}  여전히 전송 실패: {out[:60]!r}"); continue
    sc = ns["extract_json"](out)
    if sc is None:
        print(f"  {p['id']}  JSON 파싱 실패 (모델 출력 문제)"); continue
    sc.setdefault("id", p["id"])
    passed, reasons = run_gates(sc)
    r.update(gates_passed=passed, reasons=reasons, scenario=sc)
    print(f"  {p['id']}  검사 {passed}/3")
json.dump(res, open(os.path.join(HERE, "generated_L.json"), "w"), ensure_ascii=False, indent=1)
print("통과:", sum(1 for r in res if r["gates_passed"] == 3), "/", len(res))
