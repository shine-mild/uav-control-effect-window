#!/bin/bash
# 무재밍 대조 30회 + 서명 실험 OFF/ON 각 30회. 대기 없이 바로 실행한다.
set -u
P="$(cd "$(dirname "$0")" && pwd)"
AP="${ARDUPILOT_PATH:-$HOME/ardupilot}"
LOG="$P/chain_progress.log"
: > "$LOG"
cd "$AP" || exit 1

sitl() {
  pkill -x arducopter 2>/dev/null; sleep 2
  ./build/sitl/bin/arducopter -S -I0 --model + --speedup 1 \
     --defaults Tools/autotest/default_params/copter.parm \
     --home 34.7604,127.6622,0,0 > "$P/sitl_rest.log" 2>&1 &
  sleep 6
}

echo "### 무재밍 대조 30회  시작 $(date +%H:%M:%S) ###" >> "$LOG"
for R in $(seq 1 30); do
  sitl
  echo "[nojam $R/30] $(date +%H:%M:%S)" >> "$LOG"
  ARDUPILOT_PATH="$AP" timeout 300 python3 -u "$P/nojam_test.py" "$R" >> "$LOG" 2>&1 \
    || echo "   ★실패 nojam $R" >> "$LOG"
done

echo "" >> "$LOG"; echo "### 서명 실험 OFF/ON 각 30회  시작 $(date +%H:%M:%S) ###" >> "$LOG"
for R in $(seq 1 30); do
  for C in OFF ON; do
    sitl
    echo "[sign $C $R/30] $(date +%H:%M:%S)" >> "$LOG"
    ARDUPILOT_PATH="$AP" timeout 320 python3 -u "$P/signing_test.py" "$C" "$R" >> "$LOG" 2>&1 \
      || echo "   ★실패 sign $C $R" >> "$LOG"
  done
done

pkill -x arducopter 2>/dev/null
echo "" >> "$LOG"; echo "ALL CHAIN DONE $(date +%H:%M:%S)" >> "$LOG"
