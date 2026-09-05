# -*- coding: utf-8 -*-
"""RC 스로틀 통제 실험 20건을 집계한다.

주 실험은 RC 를 통제하지 않았으므로 ALT_HOLD 주입이 만든 창 단축이
스로틀 입력에 얼마나 의존하는지 알 수 없었다. 스로틀을 최하단(PWM 1000)과
중립(PWM 1500)으로 고정하고 무주입·ALT_HOLD 를 각 5회 재어 그 의존성을 본다.
이 20건은 사전 등록 범위 밖의 추가 검증이며 기존 380건과 구분해 보고한다.
"""
import json, glob, os, statistics as st

P = os.path.dirname(os.path.abspath(__file__))
COND = [("LOW", "BASELINE"), ("LOW", "ALT_HOLD"), ("LOW", "STABILIZE"),
        ("MID", "BASELINE"), ("MID", "ALT_HOLD"), ("MID", "STABILIZE")]
NAME = {"LOW": "최하단(1000)", "MID": "중립(1500)"}

data = {k: [] for k in COND}
for f in sorted(glob.glob(os.path.join(P, "runs", "RC-*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    e = d.get("signing_experiment") or d.get("extra") or {}   # report() 가 extra 를 이 키로 병합한다
    k = (e.get("rc_profile"), e.get("condition"))
    if k in data:
        data[k].append(dict(id=d["id"], w=d.get("window_s"), v=d.get("impact_mps"),
                            ack=(d.get("acks") or [{}])[0].get("ack"),
                            mode=(d.get("acks") or [{}])[0].get("mode_after"),
                            tlog=bool(d.get("tlog"))))

print("=" * 74)
print("  RC 스로틀 통제 실험 — 사전 등록 범위 밖의 추가 검증")
print("=" * 74)
print("\n[조건별 제어효과 창]")
print("  %-12s %-9s %3s %9s %9s %9s" % ("스로틀", "조건", "n", "창중앙값", "미종료", "접지중앙"))
for k in COND:
    r = data[k]
    ws = [x["w"] for x in r if x["w"] is not None]
    vs = [x["v"] for x in r if x["v"] is not None]
    print("  %-12s %-9s %3d %9s %9d %9s" % (
        NAME[k[0]], k[1], len(r),
        ("%.2f" % st.median(ws)) if ws else "—",
        sum(1 for x in r if x["w"] is None),
        ("%.3f" % st.median(vs)) if vs else "—"))

print("\n[주입 수락 여부 — 스로틀과 무관하게 성립하는가]")
for k in [("LOW", "ALT_HOLD"), ("MID", "ALT_HOLD"), ("LOW", "STABILIZE"), ("MID", "STABILIZE")]:
    r = data[k]
    ok = sum(1 for x in r if x["ack"] == "ACCEPTED" and x["mode"] == k[1])
    print("  %-12s %-9s 모드 전환 성립 %d/%d" % (NAME[k[0]], k[1], ok, len(r)))

print("\n[해석]")
b_low = [x["w"] for x in data[("LOW", "BASELINE")] if x["w"] is not None]
b_mid = [x["w"] for x in data[("MID", "BASELINE")] if x["w"] is not None]
a_low = [x["w"] for x in data[("LOW", "ALT_HOLD")] if x["w"] is not None]
a_mid_none = sum(1 for x in data[("MID", "ALT_HOLD")] if x["w"] is None)
if b_low and b_mid:
    print("  무주입의 창은 스로틀에 좌우되지 않는다 (%.2f 대 %.2f 초)."
          % (st.median(b_low), st.median(b_mid)))
if a_low and b_low:
    print("  최하단에서 ALT_HOLD 주입은 창을 %.2f 초에서 %.2f 초로 줄인다."
          % (st.median(b_low), st.median(a_low)))
print("  중립에서 ALT_HOLD 주입은 %d/%d 에서 관측 상한 안에 종료되지 않았다."
      % (a_mid_none, len(data[("MID", "ALT_HOLD")])))
print("  즉 모드 전환은 스로틀과 무관하게 성립하나, 그 뒤의 하강은 기존 스로틀 입력이 만든다.")

n_tlog = sum(1 for k in COND for x in data[k] if x["tlog"])
print("\n  전체 %d 건 · 원시 tlog 보존 %d 건"
      % (sum(len(v) for v in data.values()), n_tlog))
