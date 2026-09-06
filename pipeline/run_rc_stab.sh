#!/bin/bash
# STABILIZE 를 각 스로틀에서 3회씩 더 재어 n = 2 를 n = 5 로 올린다.
set -u
P="$(cd "$(dirname "$0")" && pwd)"
AP="${ARDUPILOT_PATH:-$HOME/ardupilot}"
# rc_test.py 는 runtime 보다 먼저 pymavlink 를 부른다 — 경로를 직접 준다
export PYMAVLINK_PATH="${PYMAVLINK_PATH:-$AP/modules/mavlink}"
LOG="$P/rc_stab_progress.log"
: > "$LOG"
cd "$AP" || exit 1

sitl() {
  pkill -x arducopter 2>/dev/null; sleep 2
  ./build/sitl/bin/arducopter -S -I0 --model + --speedup 1 \
     --defaults Tools/autotest/default_params/copter.parm \
     --home 34.7604,127.6622,0,0 > "$P/sitl_rc_stab.log" 2>&1 &
  sleep 6
}

for R in 03 04 05; do
  for PR in LOW MID; do
    sitl
    echo "[$PR STABILIZE $R] $(date +%H:%M:%S)" >> "$LOG"
    ARDUPILOT_PATH="$AP" PYMAVLINK_PATH="$PYMAVLINK_PATH" timeout 420 python3 -u "$P/rc_test.py" "$PR" STABILIZE "$R" >> "$LOG" 2>&1 \
      || echo "   ★실패 $PR STABILIZE $R" >> "$LOG"
  done
done
pkill -x arducopter 2>/dev/null
echo "### 완료 $(date +%H:%M:%S) ###" >> "$LOG"
