# -*- coding: utf-8 -*-
"""저장된 판정 JSON 을 대조군 실측값으로 재분류한다.

BASELINE_W 를 코드에 하드코딩하지 않고, 같은 조건의 대조군 실행에서 얻은 값을 쓴다.
분류 규칙: extend(w1 > w0), destroy(공중종료 또는 접지 v > 임계), recover(그 외).
"""
import json, glob, os
HERE = os.path.dirname(os.path.abspath(__file__))
IMPACT_DESTROY = 5.0

runs = {}
for f in glob.glob(os.path.join(HERE, "runs", "*.json")):
    j = json.load(open(f, encoding="utf-8")); runs[j["id"]] = j

base = runs.get("BASELINE")
if not base or base.get("window_s") is None:
    raise SystemExit("대조군 실행 결과가 없다. BASELINE 을 먼저 실행할 것.")
W0, V0 = base["window_s"], base["impact_mps"]
print(f"대조군(실측)  창 w0 = {W0} s | 접지 v0 = {V0} m/s\n")

hdr = f"{'ID':<9}{'명령':<26}{'창(s)':>8}{'접지':>8}{'공중종료':>9}{'재분류':>9}{'기대':>9}{'일치':>6}{'사슬':>6}"
print(hdr); print("-"*len(hdr))
out = []
for sid in sorted(k for k in runs if k != "BASELINE"):
    j = runs[sid]
    w1, v = j["window_s"], j["impact_mps"]
    tia = j.get("terminated_in_air")
    if w1 is None:                       oc = None
    elif w1 > W0:                        oc = "extend"
    elif tia:                            oc = "destroy"
    elif v is not None and v > IMPACT_DESTROY: oc = "destroy"
    else:                                oc = "recover"
    cmd = j["acks"][0]["cmd"] if j.get("acks") else "-"
    match = (oc == j.get("expected_outcome"))
    j["outcome_reclassified"] = oc
    j["baseline_window_s"] = W0
    j["outcome_match_reclassified"] = match
    json.dump(j, open(os.path.join(HERE, "runs", sid + ".json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"{sid:<9}{cmd:<26}{(w1 if w1 is not None else 0):>8.2f}"
          f"{(v if v is not None else float('nan')):>8.2f}{str(tia):>9}"
          f"{str(oc):>9}{str(j.get('expected_outcome')):>9}"
          f"{'O' if match else 'X':>6}{'O' if j.get('chain_reproduced') else 'X':>6}")
    out.append(dict(id=sid, cmd=cmd, window_s=w1, impact=v, terminated_in_air=tia,
                    outcome=oc, expected=j.get("expected_outcome"), match=match,
                    chain=j.get("chain_reproduced"), failures=j.get("failures")))

n = len(out)
print(f"\n사슬 재현 {sum(1 for r in out if r['chain'])}/{n}"
      f" | 사후상태 일치 {sum(1 for r in out if r['match'])}/{n}")
for r in out:
    if r["failures"]: print(f"  [!] {r['id']}: {r['failures']}")
json.dump(dict(baseline_window_s=W0, baseline_impact=V0, runs=out),
          open(os.path.join(HERE, "reclassified.json"), "w"), ensure_ascii=False, indent=1)
print("[+] reclassified.json 기록")
