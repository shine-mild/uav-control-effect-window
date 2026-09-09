"""Offline RC30 analysis. No SITL or network connection is opened.

python analyze_rc30.py --runs runs --out summary.json
python analyze_rc30.py --runs runs --tlogs EXTRACTED/tlogs --out replay.json
Summary-only uses the stdlib. Raw replay additionally requires pymavlink.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics as st
import time

def replay(path):
    from pymavlink import mavutil
    m=mavutil.mavlink_connection(str(path),dialect='ardupilotmega')
    sim=0;alt=0;armed=False;landed=0;tm=td=tl=None;impact=None;rc=set();modes=[]
    last_hb=None;max_gap=0;speedup=[]
    while (msg:=m.recv_match()) is not None:
        if msg.get_type()=='BAD_DATA' or msg.get_srcSystem()!=1:continue
        typ=msg.get_type()
        if typ=='GLOBAL_POSITION_INT':sim=msg.time_boot_ms;alt=msg.relative_alt/1000
        elif typ=='HEARTBEAT':
            if last_hb is not None and tm is not None:max_gap=max(max_gap,msg._timestamp-last_hb)
            last_hb=msg._timestamp
            ar=bool(msg.base_mode&128)
            if armed and not ar and tm is not None and td is None:td=sim
            armed=ar
            if ar and msg.custom_mode==9 and tm is None:tm=sim
            if tm is not None:modes.append(msg.custom_mode)
        elif typ=='EXTENDED_SYS_STATE':
            if msg.landed_state==1 and landed!=1 and tm is not None and td is None and alt<=10 and tl is None:tl=sim
            landed=msg.landed_state
        elif typ=='RC_CHANNELS' and tm is not None:rc.add(msg.chan3_raw)
        elif typ=='PARAM_VALUE' and msg.param_id=='SIM_SPEEDUP':speedup.append(msg.param_value)
        elif typ=='STATUSTEXT' and 'Hit ground at' in msg.text:
            impact=float(msg.text.split('Hit ground at')[1].split('m/s')[0])
    m.close()
    end=min((v for v in (td,tl) if v is not None),default=None)
    return dict(window_s=round((end-tm)/1000,3) if tm is not None and end is not None else None,
        followup_s=round((sim-tm)/1000,3) if tm is not None else None,
        impact_mps=impact,rc_values=sorted(rc),modes=sorted(set(modes)),
        post_land_hb_gap_s=max_gap,speedup_values=speedup,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def analyze(runs,tlogs=None,wait_for_records=False):
    groups={};raw=[]
    for t in ('LOW','MID'):
        for c in ('BASELINE','ALT_HOLD','STABILIZE'):
            ds=[]
            for rep in range(1,31):
                sid=f'RC30-{t}-{c}-{rep:02d}'
                record=runs/(sid+'.json')
                deadline=time.monotonic()+3600
                while wait_for_records and not record.exists():
                    if time.monotonic()>deadline:raise TimeoutError('Missing '+sid)
                    time.sleep(5)
                d=json.loads(record.read_text(encoding='utf-8'))
                assert d['id']==sid and d['protocol']=='RC30-sim200-speed5-v2'
                assert d['ok'] and d['speedup_verified']==5 and d['rc_observed_values']==[d['rc_pwm']]
                assert d['censored']==(d['window_s'] is None)
                if d['censored']:assert d['followup_s']>=200
                ds.append(d)
                if tlogs:
                    r=replay(tlogs/(sid+'.tlog'));r['id']=sid
                    assert r['window_s']==d['window_s'] and r['impact_mps']==d['impact_mps'],sid
                    assert r['sha256']==d['tlog_sha256'] and r['rc_values']==[d['rc_pwm']],sid
                    assert r['post_land_hb_gap_s']<3 and r['speedup_values'][-1]==5,sid
                    mode={'ALT_HOLD':2,'STABILIZE':0}.get(c,-1)
                    assert (mode in r['modes'])==d['mode_changed'],sid
                    assert r['followup_s']==d['followup_s'],sid
                    raw.append(r);print('RAW VERIFIED',sid,flush=True)
            times=[d['window_s'] for d in ds if d['window_s'] is not None]
            impacts=[d['impact_mps'] for d in ds if d['impact_mps'] is not None]
            groups[t+'_'+c]=dict(n=30,ended=len(times),censored=30-len(times),
                mode_changed=sum(d['mode_changed'] for d in ds),
                median_s=st.median(times) if times else None,range_s=[min(times),max(times)] if times else None,
                impact_n=len(impacts),impact_median=st.median(impacts) if impacts else None,
                followup_range=[min(d['followup_s'] for d in ds),max(d['followup_s'] for d in ds)])
    return dict(groups=groups,raw_verified=len(raw),raw_records=raw,
        note='RC30 v2 only. Censored times are not treated as events at 200s. No pooling with historical RC or pilot-v1.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,default=Path(__file__).parent/'runs')
    p.add_argument('--tlogs',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--wait-for-records',action='store_true');a=p.parse_args()
    result=analyze(a.runs,a.tlogs,a.wait_for_records)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['groups'],ensure_ascii=False,indent=2))
