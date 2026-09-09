"""Isolated local-only RC30 SITL suite. Dedicated state/ports, no global pkill.

Linux: python3 rc30_suite.py --work WORK --ap ARDUPILOT --runtime RUNTIME --pilot
Omit --pilot for a complete 30 x 6 design (pilot files are preserved/reused).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True)
    p.add_argument('--ap',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--pilot',action='store_true');a=p.parse_args()
    a.work.mkdir(parents=True,exist_ok=True)
    if not (a.work/'runtime.py').exists():shutil.copy2(a.runtime,a.work/'runtime.py')
    worker=Path(__file__).with_name('rc30_worker.py').resolve()
    env=os.environ.copy();env['ARDUPILOT_PATH']=str(a.ap);env['PYMAVLINK_PATH']=str(a.ap/'modules/mavlink')
    manifest=dict(protocol='RC30-sim200-speed5-v2',repetitions=30,conditions=6,
        followup_sim_s=200,speedup=5,workers=6,
        commit=subprocess.check_output(['git','-C',str(a.ap),'rev-parse','HEAD'],text=True).strip(),
        runtime_sha256=hashlib.sha256((a.work/'runtime.py').read_bytes()).hexdigest(),
        worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),
        note='New complete RC series. Not pooled with historical RC or pilot-v1 trials. Fixed simulated follow-up, post-takeoff speed verification, and explicit tlog flush. Deterministic isolated processes are implementation repeats, not independent real vehicles.')
    (a.work/'protocol.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    combos=[(t,c) for t in ('LOW','MID') for c in ('BASELINE','ALT_HOLD','STABILIZE')]
    def lane(item):
        idx,(profile,cond)=item;instance=20+idx
        state=a.work/('state'+str(instance));state.mkdir(exist_ok=True)
        for rep in range(1,2 if a.pilot else 31):
            sid=f'RC30-{profile}-{cond}-{rep:02d}'
            if (a.work/'runs'/(sid+'.json')).exists():
                print('EXISTS',sid,flush=True);continue
            log=a.work/(sid+'.stdout.txt')
            with (state/'sitl.log').open('w') as sf,log.open('w') as lf:
                sitl=subprocess.Popen([str(a.ap/'build/sitl/bin/arducopter'),'-S','-I'+str(instance),'-w',
                    '--model','+','--speedup','5','--defaults',str(a.ap/'Tools/autotest/default_params/copter.parm'),
                    '--home','34.7604,127.6622,0,0'],cwd=state,stdout=sf,stderr=subprocess.STDOUT,env=env)
                try:
                    time.sleep(3)
                    cp=subprocess.run([sys.executable,'-u',str(worker),'--work',str(a.work),'--profile',profile,
                        '--condition',cond,'--rep',str(rep),'--instance',str(instance)],
                        stdout=lf,stderr=subprocess.STDOUT,env=env,timeout=360)
                    if cp.returncode:raise RuntimeError('Worker failed: '+sid+'; inspect '+str(log))
                    d=json.loads((a.work/'runs'/(sid+'.json')).read_text())
                    if not d['ok']:raise RuntimeError('Invalid run retained: '+sid)
                    print('DONE',sid,d['window_s'],'censored',d['censored'],flush=True)
                finally:
                    sitl.terminate()
                    try:sitl.wait(timeout=8)
                    except subprocess.TimeoutExpired:sitl.kill();sitl.wait()
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lane,enumerate(combos)))
    print('SUITE COMPLETE',flush=True)

if __name__=='__main__':main()
