#!/bin/bash
# 스크립트마다 새 SITL 인스턴스를 띄워 실행한다. 시행 간 상태를 물려주지 않는다.
set -u
W="$(cd "$(dirname "$0")" && pwd)"
AP="${ARDUPILOT_PATH:-$HOME/ardupilot}"
export PYMAVLINK_PATH="$AP/modules/mavlink"
COND="$1"
cd "$AP" || exit 1
for f in "$W/scripts_$COND"/*.py; do
  [ -e "$f" ] || { echo "실행할 스크립트 없음"; exit 0; }
  N=$(basename "$f" .py)
  [ -f "$W/runs/$N.json" ] && { echo "skip $N"; continue; }
  pkill -x arducopter 2>/dev/null; sleep 2
  ./build/sitl/bin/arducopter -I0 --model + --speedup 1 \
     --defaults Tools/autotest/default_params/copter.parm \
     --home 34.7604,127.6622,0,0 > "$W/sitl_$N.log" 2>&1 &
  sleep 6
  echo "########## $N ##########"
  timeout 400 python3 -u "$f" 2>&1 | grep -E "^\[|^ *\[sim|Traceback|Error|재현|판정" | tail -20
done
pkill -x arducopter 2>/dev/null
echo "### $COND 완료 ###"
