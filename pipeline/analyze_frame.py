#!/usr/bin/env python3
"""기종 3종(quad/hexa/octa) 수락·거부 집합과 창의 일치 여부 대조."""
import json, glob, os, statistics as st
P = os.path.dirname(os.path.abspath(__file__))
CONDS = ["ALT_HOLD","STABILIZE","DISARM","GUIDED_NOGPS","FLIGHTTERMINATION",
         "AUTO","BRAKE","GUIDED","LOITER","POSHOLD","RTL","SMART_RTL"]

def rd(f):
    try: return json.load(open(f))
    except Exception: return None

def ack_of(d):
    for e in d.get("acks", []) or []:
        r = (e.get("ack") or e.get("result")) if isinstance(e, dict) else None
        if r: return r
    for e in reversed(d.get("events", [])):
        t = e.get("detail","")
        if "ack=" in t: return t.split("ack=")[1].split()[0]
    return "?"

def cell(pat, nmax=30):
    out=[]
    for f in sorted(glob.glob(os.path.join(P,"runs",pat))):
        b=os.path.basename(f).rsplit("-",1)[-1].split(".")[0]
        if pat.endswith("-*.json") and (not b.isdigit() or not (1 <= int(b) <= nmax)): continue
        d=rd(f)
        if d: out.append(d)
    return out

FRAMES=[("quad","M-%s.json","R-BASELINE-*.json"),
        ("hexa","V-HEXA-%s-*.json","V-HEXA-BASELINE-*.json"),
        ("octa","V-OCTA-%s-*.json","V-OCTA-BASELINE-*.json")]

print("="*78)
print("  기종 일반화 — 40 m, variance 분기, ArduPilot SITL c2b898a")
print("="*78)
print("\n[기준선] 무주입 제어효과 창")
print(f"  {'기종':<6} {'n':>3} {'중앙값(s)':>10} {'범위':>18} {'접지(m/s)':>10}")
for name,_,bpat in FRAMES:
    ds=[d for d in cell(bpat) if d.get("window_s") is not None]
    w=sorted(d["window_s"] for d in ds)
    if not w: print(f"  {name:<6} {'—':>3}"); continue
    imp=[d["impact_mps"] for d in ds if d.get("impact_mps")]
    print(f"  {name:<6} {len(w):>3} {st.median(w):>10.2f} {min(w):>8.2f}~{max(w):<9.2f} "
          f"{(st.median(imp) if imp else float('nan')):>10.3f}")

print("\n[12종 전수] 수락·거부와 창")
hdr=f"  {'명령':<18}" + "".join(f"{n:>17}" for n,_,_ in FRAMES)
print(hdr); print("  " + "-"*(18+17*3))
disagree=[]
for c in CONDS:
    cells=[]
    for name,pat,_ in FRAMES:
        ds=cell(pat % c)
        if not ds: cells.append(("—",None)); continue
        d=ds[0]; a=ack_of(d); w=d.get("window_s")
        cells.append((a, w))
    txt=f"  {c:<18}"
    for a,w in cells:
        s = f"{a[:8]}/{w:.2f}s" if w is not None else (f"{a[:8]}" if a!="—" else "—")
        txt += f"{s:>17}"
    print(txt)
    acks=[a for a,_ in cells if a!="—"]
    if len(acks)<len(FRAMES): disagree.append((c, "미측정 " + str(acks)))
    elif len(set(acks))>1:    disagree.append((c, acks))

print("\n[집합 일치]")
if not disagree:
    print("  세 기종의 수락·거부 판정이 12종 전부에서 일치하였다.")
else:
    for c,a in disagree: print(f"  불일치: {c} → {a}")
