import json
from datetime import datetime, timezone
from pathlib import Path
from maya_service import running_pid
ROOT=Path(__file__).resolve().parent
def load_json(name, default):
    try: return json.loads((ROOT/name).read_text(encoding='utf-8'))
    except Exception: return default
def status_snapshot():
    state=load_json('maya_service_state.json',{})
    activation=load_json('maya_activation_state.json',{})
    try:
        alive=running_pid() is not None
    except Exception:
        alive=None
    if alive:
        service_status='awake'
    elif not state or state.get('status')=='unknown':
        service_status='unknown'
    else:
        service_status='sleeping'
    return {'maya':'running','service_status':service_status,'activation':{'active':bool(activation.get('active',False)),'automatic_browsing':bool(activation.get('automatic_browsing',False)),'automatic_learning':bool(activation.get('automatic_learning',False)),'presence_mode':False},'safety':{'public_research':'read_only','trusted_memory':'explicit_approval_required','application_control':'disabled'},'checked_at':datetime.now(timezone.utc).isoformat()}
def research_envelope(topic,sources):
    return {'topic':topic,'mode':'public_read_only','summary':'Research results are informational and require human review.','sources':[{'number':i,'title':x.get('title') or x.get('source') or 'Public source','url':x.get('url',''),'excerpt':x.get('excerpt','')} for i,x in enumerate(sources or [],1)],'trusted_memory_updated':False}
def observation_review():
    pending=load_json('andy_evidence_pending.jsonl',[])
    if isinstance(pending,dict): pending=pending.get('items',[])
    return {'pending_count':len(pending) if isinstance(pending,list) else 0,'items':pending if isinstance(pending,list) else [],'actions':['approve','correct','reject'],'trusted_memory_updated':False}


def record_observation_correction(text):
    item={"correction":text,"created_at":datetime.now(timezone.utc).isoformat(),"trusted_memory_updated":False}
    with (ROOT/"maya_observation_corrections.jsonl").open("a",encoding="utf-8") as handle:
        handle.write(json.dumps(item,ensure_ascii=False)+"\n")
    return item

