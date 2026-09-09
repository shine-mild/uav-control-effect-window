"""One isolated, offline SITL RC trial. Only connects to loopback TCP.

New RC30 series: fixed 200 simulation-second follow-up; not pooled with RC.
The archived runtime.py provides unchanged state/event decision rules.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ap=argparse.ArgumentParser()
ap.add_argument('--work',type=Path,required=True)
ap.add_argument('--profile',choices=('LOW','MID'),required=True)
ap.add_argument('--condition',choices=('BASELINE','ALT_HOLD','STABILIZE'),required=True)
ap.add_argument('--rep',type=int,required=True)
ap.add_argument('--instance',type=int,required=True)
a=ap.parse_args()
sys.path.insert(0,str(a.work))
sys.path.insert(0,os.environ['PYMAVLINK_PATH'])
from runtime import Runner,RESULT
from pymavlink import mavutil

sid=f'RC30-{a.profile}-{a.condition}-{a.rep:02d}'
target=a.work/'runs'/(sid+'.json')
if target.exists(): raise RuntimeError('Refusing to overwrite '+str(target))
mode={'ALT_HOLD':2,'STABILIZE':0}.get(a.condition)

class Trial(Runner):
    def __init__(self):
        super().__init__(sid,branch='variance')
        self.rc_active=False;self.rc_sent=0;self.last_rc=0
        self.rc_observed=[];self.last_nav=None
    def _handle(self,msg):
        super()._handle(msg)
        now=time.monotonic()
        if self.rc_active and now-self.last_rc>=0.08:
            self.m.mav.rc_channels_override_send(self.m.target_system,self.m.target_component,
                1500,1500,1000 if a.profile=='LOW' else 1500,1500,0,0,0,0)
            self.last_rc=now;self.rc_sent+=1
        if self.rc_active and msg.get_type()=='RC_CHANNELS' and self.t_land is not None:
            self.rc_observed.append(msg.chan3_raw)

g=Trial();wall=time.monotonic()
g.connect('tcp:127.0.0.1:'+str(5760+10*a.instance))
g.preflight();g.takeoff(40)
takeoff_alt=g.S['alt']
if g.failures or not g.S['armed'] or takeoff_alt<35:
    raise RuntimeError('Preflight/takeoff invalid: '+str(g.failures)+str(g.S))
# Historical takeoff() resets SIM_SPEEDUP to 1. Explicitly set and verify the
# new series' planned rate AFTER takeoff; pilot-v1 is retained and not pooled.
speedup=g.setp('SIM_SPEEDUP',5,critical=True)
if speedup!=5:raise RuntimeError('Planned simulation speed not confirmed')
g.pump(.4)
g.rc_active=True
def advance_sim(seconds):
    start=g.S['simms'];deadline=time.monotonic()+90
    while g.S['simms']-start<seconds*1000 and time.monotonic()<deadline:g.pump(.03)
    if time.monotonic()>=deadline:raise RuntimeError('Simulation clock stalled')
advance_sim(1.5)
g.setp('SIM_GPS1_JAM',1)
deadline=time.monotonic()+100
while g.t_land is None and time.monotonic()<deadline:g.pump(.03)
if g.t_land is None:raise RuntimeError('LAND not observed')
advance_sim(.5)
if mode is not None:
    g.t_cmd=g.S['simms'];g.injected_mode=a.condition
    g.m.mav.command_long_send(g.m.target_system,g.m.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,0,1,mode,0,0,0,0,0)
ack=None;mode_seen=False;followup_last=None
deadline=time.monotonic()+160
while g.S['simms']-g.t_land<200000 and g.t_disarm is None and g.t_onground is None:
    if time.monotonic()>deadline:raise RuntimeError('Wall-clock safety timeout before planned observation')
    msg=g.m.recv_match(blocking=True,timeout=.1)
    if msg:
        g._handle(msg)
        if msg.get_type()=='COMMAND_ACK' and msg.command==mavutil.mavlink.MAV_CMD_DO_SET_MODE:
            ack=RESULT.get(msg.result,str(msg.result))
        if mode is not None and g.S['mode']==a.condition:mode_seen=True
followup_last=g.S['simms']
ends=[v for v in (g.t_disarm,g.t_onground) if v is not None]
end=min(ends) if ends else None
window=round((end-g.t_land)/1000,3) if end is not None else None
cutoff=dict(t_disarm_ms=g.t_disarm,t_onground_ms=g.t_onground,
    last_sim_ms=followup_last,impact_mps=g.S['impact'],last_alt_m=g.S['alt'])
# Explicit flush solves the historical tail-truncation problem; no extra observation.
if getattr(g.m,'logfile',None):g.m.logfile.flush();os.fsync(g.m.logfile.fileno())
g.m.close()
record=dict(id=sid,profile=a.profile,condition=a.condition,rep=a.rep,instance=a.instance,
    protocol='RC30-sim200-speed5-v2',speedup_verified=speedup,window_s=window,censored=end is None,
    followup_s=round((followup_last-g.t_land)/1000,3),t_land_ms=g.t_land,
    mode_changed=mode_seen,ack=ack,rc_pwm=1000 if a.profile=='LOW' else 1500,
    rc_observed_values=sorted(set(g.rc_observed)),rc_messages=len(g.rc_observed),
    takeoff_alt_m=takeoff_alt,wall_s=round(time.monotonic()-wall,3),
    failures=g.failures,ok=not g.failures,chain=g.chain,events=g.events,
    tlog_sha256=hashlib.sha256(Path(g.tlog_path).read_bytes()).hexdigest(),**cutoff)
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:record[k] for k in ('id','window_s','censored','mode_changed','rc_observed_values','wall_s','ok')},ensure_ascii=False),flush=True)
