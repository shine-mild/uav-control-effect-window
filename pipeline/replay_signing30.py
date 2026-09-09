"""Independent raw replay of S4 logs. Requires pymavlink; no live connection.

Unzip CISC_원시로그_서명60건.zip, then run:
python replay_signing30.py --tlogs EXTRACTED/tlogs --runs ./runs --out replay.json
Summary timing is preserved even if the raw log lacks the final event.
"""
import argparse
import hashlib
import json
from pathlib import Path
from pymavlink import mavutil


def replay(path):
    conn=mavutil.mavlink_connection(str(path),dialect='ardupilotmega')
    sim=0; alt=0; armed=False; landed=0; tm=td=tl=None
    modes=[]; impacts=[]; signed=total=0
    while (msg:=conn.recv_match()) is not None:
        if msg.get_type()=='BAD_DATA' or msg.get_srcSystem()!=1: continue
        raw=msg.get_msgbuf()
        if tm is not None:
            total+=1
            signed+=int(len(raw)>2 and raw[0]==0xfd and bool(raw[2]&1))
        typ=msg.get_type()
        if typ=='GLOBAL_POSITION_INT': sim=msg.time_boot_ms; alt=msg.relative_alt/1000
        elif typ=='HEARTBEAT':
            a=bool(msg.base_mode & 128)
            if armed and not a and tm is not None and td is None: td=sim
            armed=a
            if armed and msg.custom_mode==9 and tm is None: tm=sim
            if tm is not None and (not modes or modes[-1][1]!=msg.custom_mode): modes.append([sim,msg.custom_mode])
        elif typ=='EXTENDED_SYS_STATE':
            if msg.landed_state==1 and landed!=1 and tm is not None and td is None and alt<=10 and tl is None: tl=sim
            landed=msg.landed_state
        elif typ=='STATUSTEXT' and 'Hit ground at' in msg.text:
            impacts.append(float(msg.text.split('Hit ground at')[1].split('m/s')[0]))
    conn.close()
    tg=min((v for v in (td,tl) if v is not None),default=None)
    return dict(window_s=round((tg-tm)/1000,2) if tm is not None and tg is not None else None,
        effective=any(mode==2 for _,mode in modes),impact_mps=impacts[-1] if impacts else None,
        mode_transitions=modes,post_land_messages=total,post_land_signed=signed,
        last_sim_ms=sim,sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest())


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--tlogs',type=Path,required=True)
    ap.add_argument('--runs',type=Path,default=Path(__file__).parent/'runs')
    ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    rows=[]
    for cond in ('OFF','ON'):
        for rep in range(1,31):
            sid=f'S4-{cond}-{rep:02d}'
            d=json.loads((a.runs/(sid+'.json')).read_text(encoding='utf-8'))
            r=replay(a.tlogs/(sid+'.tlog'));r['id']=sid;r['condition']=cond
            r['window_matches']=r['window_s']==d['window_s']
            r['impact_matches']=r['impact_mps']==d['impact_mps']
            r['effect_matches']=r['effective']==d['signing_experiment']['effective']
            r['summary_window_s']=d['window_s'];r['summary_impact_mps']=d['impact_mps']
            rows.append(r)
            print(sid,'mode:',r['effect_matches'],'time:',r['window_matches'],flush=True)
    result=dict(raw_records=rows,raw_match_counts={k:sum(r[k] for r in rows) for k in ('window_matches','effect_matches','impact_matches')})
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result['raw_match_counts'])
