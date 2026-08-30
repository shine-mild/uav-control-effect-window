# -*- coding: utf-8 -*-
"""대조군 — 교란만 주고 명령은 주입하지 않는다. 새 정의(접지 기준)로 w0 재측정."""
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from runtime import Runner
R = Runner("BASELINE", expected_outcome=None, branch="variance")
R.connect(); R.preflight(); R.takeoff(40.0)
R.setp("SIM_GPS1_JAM", 1)
R.wait("fsLand")
R.wait_end()
R.report()
