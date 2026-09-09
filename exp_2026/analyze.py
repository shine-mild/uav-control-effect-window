# -*- coding: utf-8 -*-
"""사전 등록한 판정 기준으로 두 조건을 대조한다. 기준을 사후에 바꾸지 않는다."""
import json, os, glob, math, sys
HERE = os.path.dirname(os.path.abspath(__file__))

def fisher(a,b,c,d):
    n1,n2,k,t=a+b,c+d,a+c,a+b+c+d
    def pr(x): return math.comb(n1,x)*math.comb(n2,k-x)/math.comb(t,k)
    o=pr(a)
    return min(1.0,sum(pr(x) for x in range(max(0,k-n2),min(k,n1)+1) if pr(x)<=o*(1+1e-12)))

out={}
for cond in ("L","T"):
    gen=json.load(open(os.path.join(HERE,f"generated_{cond}.json"),encoding="utf-8"))
    passed=[r for r in gen if r["gates_passed"]==3]
    runs=[]
    for r in passed:
        p=os.path.join(HERE,"runs",f"{cond}-{r['path_id']}.json")
        runs.append(json.load(open(p,encoding="utf-8")) if os.path.exists(p) else None)
    rep=[j for j in runs if j and j.get("chain_reproduced") and j.get("outcome_match") and not j.get("failures")]
    out[cond]=dict(생성=len(gen),정적통과=len(passed),실행=sum(1 for j in runs if j),재현=len(rep),
        상세=[dict(id=(f"{cond}-{r['path_id']}"),명령=r["command"],
                 실행=bool(j),사슬=(j or {}).get("chain_reproduced"),결과일치=(j or {}).get("outcome_match"),
                 관측결과=(j or {}).get("outcome"),기대=(j or {}).get("expected_outcome"),
                 실패=(j or {}).get("failures"))
              for r,j in zip(passed,runs)])
L,T=out["L"],out["T"]
out["fisher_two_sided_p"]=fisher(L["재현"],L["정적통과"]-L["재현"],T["재현"],T["정적통과"]-T["재현"])
print(json.dumps({k:(v if k!="상세" else v) for k,v in out.items()},ensure_ascii=False,indent=1))
json.dump(out,open(os.path.join(HERE,"compare_LT.json"),"w"),ensure_ascii=False,indent=1)
