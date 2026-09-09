# -*- coding: utf-8 -*-
"""T 조건 — 고정 템플릿 생성. 언어모델을 쓰지 않는다."""
import json, os, sys, builtins, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from graph import enumerate_paths
from gates import run_gates

spec = importlib.util.spec_from_file_location("bt", os.path.join(HERE, "baseline_template.py"))
bt = importlib.util.module_from_spec(spec)
_o = builtins.open
builtins.open = lambda f, *a, **k: (_ for _ in ()).throw(IOError()) if (a and 'w' in str(a[0])) else _o(f, *a, **k)
try: spec.loader.exec_module(bt)
except Exception: pass
builtins.open = _o

res = []
for p in enumerate_paths():
    sc = bt.template_scenario(p)
    passed, reasons = run_gates(sc)
    res.append(dict(path_id=p["id"], gates_passed=passed, reasons=reasons, scenario=sc,
                    expected_outcome=p["expected_outcome"], command=p["command"],
                    branch=p["branch"].split("(")[1].rstrip(")"), injection=p["injection"]))
    print(f"  {p['id']}  {p['command']:36} 검사 {passed}/3", flush=True)
json.dump(res, open(os.path.join(HERE, "generated_T.json"), "w"), ensure_ascii=False, indent=1)
print(f"\nT 조건 정적 검사 통과 {sum(1 for r in res if r['gates_passed']==3)}/{len(res)}")
