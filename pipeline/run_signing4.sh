#!/bin/bash
# 서명 대조 실험 4판 — 조건마다 시동 전에 서명 상태를 명시적으로 만든다.
set -u
P="$(cd "$(dirname "$0")" && pwd)"
AP="${ARDUPILOT_PATH:-$HOME/ardupilot}"
export PYMAVLINK_PATH="${PYMAVLINK_PATH:-$AP/modules/mavlink}"
LOG="$P/signing4_progress.log"
: > "$LOG"
cd "$AP" || exit 1

sitl() {
  pkill -x arducopter 2>/dev/null; sleep 2
  ./build/sitl/bin/arducopter -S -I0 --model + --speedup 1 \
     --defaults Tools/autotest/default_params/copter.parm \
     --home 34.7604,127.6622,0,0 > "$P/sitl_signing4.log" 2>&1 &
  sleep 6
}

for R in 1 2 3 4 5; do
  for C in OFF ON; do
    sitl
    echo "[$C $R/5] $(date +%H:%M:%S)" >> "$LOG"
    ARDUPILOT_PATH="$AP" PYMAVLINK_PATH="$PYMAVLINK_PATH" timeout 420 \
      python3 -u "$P/signing_test4.py" "$C" "$R" >> "$LOG" 2>&1 \
      || echo "   ★실패 $C $R" >> "$LOG"
  done
done
pkill -x arducopter 2>/dev/null
echo "### 완료 $(date +%H:%M:%S) ###" >> "$LOG"
