#!/bin/bash
# 2차 생성 표본 — 프롬프트·모델·게이트를 그대로 두고 독립 생성만 한 번 더 한다.
set -u
P="$(cd "$(dirname "$0")" && pwd)"
cd "$P"
python3 -u generate.py --n 10 > gen2_progress.log 2>&1
if [ -f generated.json ]; then
  mv generated.json ../data/generated_v2.json
  echo "### 기록: data/generated_v2.json ###" >> gen2_progress.log
fi
echo "### 완료 $(date +%H:%M:%S) ###" >> gen2_progress.log
