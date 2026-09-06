# -*- coding: utf-8 -*-
"""보관 중인 원시 tlog 를 그 자리에서 재판독한다.

02_검증/audit_raw.py 의 판독 논리를 그대로 쓰되 zip 대신 실제 파일을 읽는다.
RC 통제 실험이 24건에서 30건으로, 서명 대조 10건이 새로 더해지면서
배포용 zip 을 다시 만들기 전에도 대조할 수 있어야 하기 때문이다.

usage: audit_local.py <ID 접두어> [...]      예: audit_local.py RC- S4-
"""
import sys, os, json, glob, importlib.util
from pathlib import Path
sys.path.insert(0, os.environ.get("PYMAVLINK_PATH",
                os.path.join(os.path.expanduser("~"), "ardupilot", "modules", "mavlink")))

AUDIT = Path("/mnt/c/Users/ksm66/OneDrive/바탕 화면/CISC 대비자료_2/06_최종보강/02_검증/audit_raw.py")
spec = importlib.util.spec_from_file_location("audit_raw", AUDIT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

pref = sys.argv[1:] or ["RC-"]
here = Path(os.path.dirname(os.path.abspath(__file__)))
out = []
for f in sorted(glob.glob(str(here / "runs" / "*.json"))):
    rec = json.load(open(f, encoding="utf-8"))
    if not any(rec["id"].startswith(p) for p in pref):
        continue
    tl = rec.get("tlog")
    if not tl or not os.path.exists(tl):
        print(f"  [!] {rec['id']} 원시 로그 없음"); continue
    e = rec.get("signing_experiment") or {}
    e.setdefault("rc_throttle_pwm", None)          # 서명 실험은 RC 를 고정하지 않는다
    rec["signing_experiment"] = e
    r = m.reread(Path(tl), rec)
    out.append(r)
    print("  %-22s 창 %-7s 원본 %-7s 일치 %-5s 접지일치 %-5s RC %-6s 검열 %s"
          % (r["id"], r["window_s"], r["original_window_s"], r["window_matches"],
             r["impact_matches"], r["rc_matches"] if e["rc_throttle_pwm"] else "-",
             r["censored"]))
w = sum(1 for r in out if r["window_matches"] or (r["censored"] and r["original_window_s"] is None))
i = sum(1 for r in out if r["impact_matches"] or (r["censored"] and r["original_impact_mps"] is None))
print(f"\n  {len(out)}건 · 창 일치 {w} · 접지 일치 {i}")
json.dump(out, open(here / "audit_local.json", "w"), ensure_ascii=False, indent=1)
print("  [+] audit_local.json 기록")
