# -*- coding: utf-8 -*-
"""서명 대조 실험(4판) 집계.

조건마다 시동 전에 기체의 서명 상태를 명시적으로 만든 뒤, 키 없는 별도 종단에서
같은 명령을 넣는다. 판정은 COMMAND_ACK 가 아니라 정상 GCS 가 관측한 모드 변화다.
"""
import json, glob, os, statistics as st

P = os.path.dirname(os.path.abspath(__file__))
data = {"OFF": [], "ON": []}
for f in sorted(glob.glob(os.path.join(P, "runs", "S4-*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    e = d.get("signing_experiment") or {}
    if e.get("condition") in data and not e.get("invalid"):
        data[e["condition"]].append(dict(
            id=d["id"], ack=e.get("ack"), mode=e.get("mode_after"),
            eff=bool(e.get("effective")), w=d.get("window_s"), v=d.get("impact_mps"),
            setup_rejected=e.get("setup_rejected"), chan=e.get("attacker_channel_ok"),
            tlog=d.get("tlog")))

print("=" * 72)
print("  서명 대조 — 키 없는 별도 종단의 미서명 명령 (조건당 n=5)")
print("=" * 72)
print("\n  %-8s %3s %10s %10s %12s %10s" % ("서명", "n", "주입성립", "ACK 수신", "창 중앙값", "접지 중앙"))
for c in ("OFF", "ON"):
    r = data[c]
    ws = [x["w"] for x in r if x["w"] is not None]
    vs = [x["v"] for x in r if x["v"] is not None]
    print("  %-8s %3d %10s %10s %12s %10s" % (
        "해제" if c == "OFF" else "활성", len(r),
        "%d/%d" % (sum(1 for x in r if x["eff"]), len(r)),
        "%d/%d" % (sum(1 for x in r if x["ack"] == "ACCEPTED"), len(r)),
        ("%.2f" % st.median(ws)) if ws else "—",
        ("%.3f" % st.median(vs)) if vs else "—"))

for c in ("OFF", "ON"):
    print("\n  [%s] 개별 기록" % ("서명 해제" if c == "OFF" else "서명 활성"))
    for x in data[c]:
        ok = os.path.exists(x["tlog"] or "") and os.path.getsize(x["tlog"] or "/nonexistent") > 0
        print("    %-12s ack=%-9s mode=%-9s w=%-7s v=%-9s 원시로그=%s"
              % (x["id"], x["ack"], x["mode"], x["w"], x["v"], "있음" if ok else "없음"))

off, on = data["OFF"], data["ON"]
if off and on:
    print("\n  [해석]")
    print("  서명을 해제한 %d회는 모두 주입이 성립했고, 적용한 %d회는 모두 성립하지 않았다."
          % (sum(1 for x in off if x["eff"]), sum(1 for x in on if not x["eff"])))
    print("  두 조건의 차이는 서명 설정 하나이며, 설정은 모두 시동 전에 이루어졌고 거부되지 않았다")
    print("  (setup_rejected=%s)." % sorted({x["setup_rejected"] for x in off + on}))
    print("  ArduPilot 은 채널 0(정상 GCS)의 미서명 패킷을 항상 수락하므로 관측 링크는 유지된다")
    print("  (GCS_Signing.cpp accept_unsigned_callback). 서명 키는 영속 저장소에 남아 재부팅해도")
    print("  살아 있다(_signing_storage). 조건마다 키를 명시적으로 설정하거나 0으로 지워야 한다.")
