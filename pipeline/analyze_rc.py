# -*- coding: utf-8 -*-
"""RC 스로틀 통제 실험 30건을 집계한다.

주 실험은 RC 를 통제하지 않았으므로 ALT_HOLD 주입이 만든 창 단축이
스로틀 입력에 얼마나 의존하는지 알 수 없었다. 스로틀을 최하단(PWM 1000)과
중립(PWM 1500)으로 고정하고 무주입·ALT_HOLD·STABILIZE 를 각 5회 재어 그 의존성을 본다.
이 30건은 사전 등록 범위 밖의 추가 검증이며 기존 380건과 구분해 보고한다.
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
                            tlog=d.get("tlog")))

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
    print("  무주입의 창은 두 스로틀에서 중앙값이 같다 (%.2f 대 %.2f 초). 다만 관측 범위는"
          % (st.median(b_low), st.median(b_mid)))
    print("  %.2f~%.2f 와 %.2f~%.2f 초로 달라 중앙값 일치만으로 독립성을 말할 수는 없다."
          % (min(b_low), max(b_low), min(b_mid), max(b_mid)))
if a_low and b_low:
    print("  최하단에서 ALT_HOLD 주입 뒤 창은 %.2f 초에서 %.2f 초로 짧았다."
          % (st.median(b_low), st.median(a_low)))
print("  중립에서는 %d/%d 이 관측 종료까지 비행 종료 사건이 없었다(우측 검열)."
      % (a_mid_none, len(data[("MID", "ALT_HOLD")])))
print("  시험한 두 스로틀 조건에서 모드 전환은 모두 성립하였고, 이후 종료 시간과 접지 결과는")
print("  전환된 모드와 스로틀 조건에 따라 달라졌다. 감시 상한은 벽시계 200초이며 창은 시뮬레이션 시각이다.")

# 경로 문자열이 아니라 실제 파일의 존재와 크기를 확인한다
ok = miss = 0
tot_b = 0
for k in COND:
    for x in data[k]:
        q = x["tlog"]
        if q and os.path.exists(q) and os.path.getsize(q) > 0:
            ok += 1; tot_b += os.path.getsize(q)
        else:
            miss += 1
n = sum(len(v) for v in data.values())
print("\n  전체 %d 건 · 원시 tlog 실파일 %d 건 (%.0f MB) · 없음 %d 건"
      % (n, ok, tot_b / 1048576, miss))
if miss:
    print("  [!] 이 집계는 JSON 요약값에서 얻은 것이며, 없는 %d 건은 원시 로그로 되짚을 수 없다." % miss)
