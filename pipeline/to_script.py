# -*- coding: utf-8 -*-
"""게이트를 통과한 시나리오를 SITL 실행 스크립트로 변환한다.

변환은 결정적이다. 언어모델이 관여하지 않는다.
steps 의 네 문법을 그대로 MAVLink 호출로 옮긴다.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gates import STEP_SET, STEP_OBSERVE, STEP_SEND, STEP_WAIT

HEAD = '''# -*- coding: utf-8 -*-
"""자동 생성됨 — 경로 {pid} (분기 {branch}) / 생성물 id {sid}. 수정하지 말 것."""
import sys, os, time, json
# pymavlink 위치는 환경변수로 준다. 없으면 설치본을 쓴다.
_mav = os.environ.get("PYMAVLINK_PATH")
if _mav:
    sys.path.insert(0, _mav)
from pymavlink import mavutil
mav = mavutil.mavlink
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from runtime import Runner

R = Runner("{pid}", expected_outcome="{outcome}", branch="{branch}")
R.connect()
R.preflight()
R.takeoff(40.0)
'''
TAIL = '''
R.wait_end()
R.report()
'''

MODES = {"STABILIZE": 0, "ALT_HOLD": 2, "GUIDED_NOGPS": 20}


def convert(sc, path_id, outcome, branch, here):
    lines = [HEAD.format(sid=sc["id"], pid=path_id, outcome=outcome, branch=branch, here=here)]
    sent = False
    for st in sc["steps"]:
        s = re.sub(r"^t\d+\s+|^t\?\s+", "", st.strip())
        if m := STEP_SET.match(s):
            lines.append(f'R.setp("{m.group(1)}", {m.group(2)})')
        elif m := STEP_OBSERVE.match(s):
            lines.append(f'R.observe("{m.group(1)}")')
        elif m := STEP_SEND.match(s):
            c = m.group(1)
            if "(" in c:
                base, arg = c.split("(")[0], c.split("(")[1].rstrip(")")
                lines.append(f'R.send_mode("{arg}", {MODES[arg]})')
            else:
                lines.append(f'R.send_cmd(mav.{c})')
            sent = True
        elif m := STEP_WAIT.match(s):
            lines.append(f'R.wait("{m.group(1)}")')
    if not sent:
        raise ValueError("주입 명령이 없다")
    lines.append(TAIL)
    return "\n".join(lines)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    res = json.load(open(os.path.join(here, "generated.json"), encoding="utf-8"))
    outdir = os.path.join(here, "scripts"); os.makedirs(outdir, exist_ok=True)
    ok = fail = 0
    for r in res:
        if r["gates_passed"] != 3:
            continue
        try:
            code = convert(r["scenario"], r["path_id"], r["expected_outcome"], r.get("branch","?"), here)
            fn = os.path.join(outdir, f"{r['path_id']}.py")
            open(fn, "w", encoding="utf-8").write(code)
            ok += 1
            print(f"  {r['path_id']}  ->  scripts/{r['path_id']}.py")
        except Exception as e:
            fail += 1
            print(f"  {r['path_id']}  변환 실패: {e}")
    print(f"\n변환 {ok}건 성공, {fail}건 실패")


if __name__ == "__main__":
    main()
