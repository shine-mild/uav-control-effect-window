"""Recompute S4 signing comparison from immutable summaries (Python stdlib).

Usage: python analyze_signing30.py [--runs PATH] [--audit PATH]
Only S4-ON/OFF-01..30 are included. Old SIGN/S3 records are not interchangeable.
Raw replay evidence is separately reported; no path-string count is called a log audit.
"""
import argparse
import json
import math
import statistics as st
from pathlib import Path


def fisher_two_sided(a,b,c,d):
    n1,n2=a+b,c+d
    total=n1+n2
    k=a+c
    def prob(x):
        return math.comb(n1,x)*math.comb(n2,k-x)/math.comb(total,k)
    observed=prob(a)
    return min(1.0,sum(prob(x) for x in range(max(0,k-n2),min(k,n1)+1) if prob(x)<=observed*(1+1e-12)))


def summarize(runs):
    groups={}
    for cond in ('OFF','ON'):
        rs=[]
        for rep in range(1,31):
            sid=f'S4-{cond}-{rep:02d}'
            p=runs/(sid+'.json')
            if not p.exists(): raise ValueError(f'Missing expected record: {sid}')
            d=json.loads(p.read_text(encoding='utf-8'))
            e=d['signing_experiment']
            if d['id']!=sid or not d['ok'] or e.get('invalid') or e['setup_rejected'] or not e['window_entered']:
                raise ValueError(f'Invalid experimental prerequisite: {sid}')
            if bool(e['effective'])!=(e['mode_after']=='ALT_HOLD'): raise ValueError(sid)
            rs.append(d)
        ws=[d['window_s'] for d in rs]
        vs=[d['impact_mps'] for d in rs if d['impact_mps'] is not None]
        groups[cond]=dict(n=len(rs),effective=sum(d['signing_experiment']['effective'] for d in rs),
            accepted=sum(d['signing_experiment']['ack']=='ACCEPTED' for d in rs),
            median_s=st.median(ws),range_s=[min(ws),max(ws)],impact_n=len(vs),median_impact_mps=st.median(vs))
    off,on=groups['OFF'],groups['ON']
    return dict(groups=groups,fisher_two_sided_p=fisher_two_sided(off['effective'],30-off['effective'],on['effective'],30-on['effective']),
        timing_source='Execution summaries, not a claim that every endpoint is present in raw telemetry.')


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--runs',type=Path,default=Path(__file__).parent/'runs')
    ap.add_argument('--audit',type=Path)
    a=ap.parse_args()
    result=summarize(a.runs)
    if a.audit:
        raw=json.loads(a.audit.read_text(encoding='utf-8'))
        assert len(raw['raw_records'])==60
        result['separate_raw_audit_match_counts']=raw['raw_match_counts']
    print(json.dumps(result,ensure_ascii=False,indent=2))
