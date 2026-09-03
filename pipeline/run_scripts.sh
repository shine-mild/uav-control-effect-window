#!/bin/bash
# 게이트를 통과해 변환된 시나리오 스크립트를 각각 새 SITL 인스턴스에서 실행한다.
# 시나리오 사이에 상태를 초기화하지 않으면 판정이 성립하지 않는다(IV 4.5).
P=/tmp/claude-1000/-home-shine/0b8ef378-5a73-47ce-bdf3-e728d3790c50/scratchpad/pipeline
export ARDUPILOT_PATH="${ARDUPILOT_PATH:-$HOME/ardupilot}"
export PYMAVLINK_PATH="$ARDUPILOT_PATH/modules/mavlink"
cd "$ARDUPILOT_PATH"
for f in $P/scripts/*.py; do
  [ -e "$f" ] || { echo "실행할 스크립트 없음"; exit 0; }
  N=$(basename "$f" .py)
  pkill -x arducopter 2>/dev/null; sleep 2
  ./build/sitl/bin/arducopter -S -I0 --model + --speedup 1 \
     --defaults Tools/autotest/default_params/copter.parm \
     --home 34.7604,127.6622,0,0 > $P/sitl_$N.log 2>&1 &
  sleep 5
  echo "########## $N ##########"
  timeout 320 python3 -u "$f" 2>&1 | grep -E "^\[|^      |^    \[sim|Traceback|Error"
done
pkill -x arducopter 2>/dev/null
echo "ALL DONE"
