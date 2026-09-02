#!/bin/bash
# 중단 지점 재개: 고도 결번 3회 + 기종 일반화 34회
set -u
P="$(cd "$(dirname "$0")" && pwd)"; AP="${ARDUPILOT_PATH:-$HOME/ardupilot}"
LOG="$P/variant_progress.log"; cd "$AP" || exit 1
echo "" >> "$LOG"; echo "### 재개 $(date +%H:%M:%S) ###" >> "$LOG"

run() {   # $1 모델  $2 고도  $3 태그  $4 조건  $5 반복
  [ -f "$P/runs/V-$3-$4-$(printf %02d $5).json" ] && return 0
  case "$1" in
    hexa) PARM="copter.parm,copter-hexa.parm" ;;
    octa) PARM="copter.parm,copter-octa.parm" ;;
    *)    PARM="copter.parm" ;;
  esac
  pkill -x arducopter 2>/dev/null; sleep 2
  ./build/sitl/bin/arducopter -S -I0 --model "$1" \
     --defaults "$(echo "$PARM" | sed 's|[^,]*|Tools/autotest/default_params/&|g')" \
     --home 34.7604,127.6622,0,0 --speedup 1 > "$P/sitl_var.log" 2>&1 &
  sleep 6
  echo "[$3 $4 $5] $(date +%H:%M:%S)" >> "$LOG"
  ARDUPILOT_PATH="$AP" timeout 400 python3 -u "$P/variant_test.py" "$4" "$5" "$2" "$3" >> "$LOG" 2>&1 \
    || echo "   ★실패 $3 $4 $5" >> "$LOG"
}

run "+" 20 ALT20 ALT_HOLD 10
run "+" 60 ALT60 BASELINE 10
run "+" 60 ALT60 ALT_HOLD 10

echo "" >> "$LOG"; echo "### B. 기종 일반화 ###" >> "$LOG"
for M in hexa octa; do
  for R in 1 2 3 4 5; do run "$M" 40 "${M^^}" BASELINE "$R"; done
  for C in ALT_HOLD STABILIZE DISARM GUIDED_NOGPS FLIGHTTERMINATION \
           AUTO BRAKE GUIDED LOITER POSHOLD RTL SMART_RTL; do
    run "$M" 40 "${M^^}" "$C" 1
  done
done
pkill -x arducopter 2>/dev/null
echo "" >> "$LOG"; echo "ALL VARIANTS DONE $(date +%H:%M:%S)" >> "$LOG"
