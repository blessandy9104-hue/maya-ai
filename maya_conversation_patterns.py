import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCES={'british_council':{'name':'British Council LearnEnglish','urls':['https://learnenglish.britishcouncil.org/free-resources/speaking','https://learnenglish.britishcouncil.org/free-resources/listening']},'common_voice':{'name':'Mozilla Common Voice','urls':['https://commonvoice.mozilla.org/']},'gutenberg':{'name':'Project Gutenberg','urls':['https://www.gutenberg.org/']}}
PROPOSALS=ROOT/'maya_conversation_pattern_proposals.jsonl'
APPROVED=ROOT/'maya_conversation_pattern_library.jsonl'
def now(): return datetime.now(timezone.utc).isoformat()
def append(path,item):
    with path.open('a',encoding='utf-8') as handle: handle.write(json.dumps(item,ensure_ascii=False)+'\n')
def read(path):
    if not path.exists(): return []
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    return out
def source_directory():
    return {'mode':'allowlist_only','sources':SOURCES,'auto_fetch':False,'trusted_memory_updated':False}
def propose(topic,situation,pattern,function,register,source_url,confidence='provisional'):
    item={'id':str(uuid.uuid4())[:8],'topic':topic,'situation':situation,'pattern':pattern,'function':function,'register':register,'source_url':source_url,'confidence':confidence,'state':'pending_review','created_at':now(),'trusted_memory_updated':False}
    append(PROPOSALS,item); return item
def review(): return {'pending':read(PROPOSALS),'approved':read(APPROVED),'approval_required':True,'trusted_memory_updated':False}
def approve(identifier):
    pending=read(PROPOSALS)
    for item in pending:
        if item.get('id')==identifier:
            item['state']='approved'; item['approved_at']=now(); item['trusted_memory_updated']=False; append(APPROVED,item); return item
    return {'error':'proposal_not_found','id':identifier,'trusted_memory_updated':False}
def correct(identifier,text):
    item={'id':identifier,'correction':text,'state':'correction_pending','created_at':now(),'trusted_memory_updated':False}; append(PROPOSALS,item); return item
def help_text(): return 'Pattern commands: :pattern sources | :pattern review | :pattern propose | topic | situation | pattern | function | register | source_url | :pattern approve ID | :pattern correct ID | correction'


