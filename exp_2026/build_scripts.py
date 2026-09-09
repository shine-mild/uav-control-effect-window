# -*- coding: utf-8 -*-
"""통과한 시나리오를 실행 스크립트로 변환한다. to_script.convert 를 그대로 쓴다.

두 조건의 실행 기록이 섞이지 않도록 실행 식별자에 조건 접두어를 붙인다.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from to_script import convert

cond = sys.argv[1]                      # 'L' 또는 'T'
src = os.path.join(HERE, f"generated_{cond}.json")
out = os.path.join(HERE, f"scripts_{cond}"); os.makedirs(out, exist_ok=True)
n = f = 0
for r in json.load(open(src, encoding="utf-8")):
    if r["gates_passed"] != 3: continue
    sid = f"{cond}-{r['path_id']}"
    try:
        code = convert(r["scenario"], sid, r["expected_outcome"], r.get("branch", "?"), HERE)
        open(os.path.join(out, sid + ".py"), "w", encoding="utf-8").write(code)
        n += 1
    except Exception as e:
        f += 1; print(f"  {sid} 변환 실패: {e}")
print(f"{cond}: 변환 {n}건, 실패 {f}건")
