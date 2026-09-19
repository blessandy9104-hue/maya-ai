import json, time, urllib.request
from maya_intent_cues import classify_opening
cases=["Although I asked what Maya can do, compare local and cloud.","Can Maya self-evolve, not rewrite permissions?","Which is better, however, why?","Rather than answer, compare choices."]
for sentence in cases:
    start=time.perf_counter()
    for _ in range(1000): classify_opening(sentence)
    elapsed=(time.perf_counter()-start)/1000*1000
    print(json.dumps({"sentence":sentence,"classifier_ms_per_call":round(elapsed,4),"intent":classify_opening(sentence)},ensure_ascii=False))
def model_probe(sentence):
    intent=classify_opening(sentence)
    messages=[{"role":"system","content":"You are Maya. Use this structured intent only as a hint: "+json.dumps(intent,ensure_ascii=False)},{"role":"user","content":sentence}]
    payload=json.dumps({"model":"qwen2.5-coder:3b","messages":messages,"stream":False,"options":{"num_ctx":640,"num_predict":24,"temperature":0.2,"num_thread":4}}).encode()
    request=urllib.request.Request("http://127.0.0.1:11434/api/chat",data=payload,headers={"Content-Type":"application/json"})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=8) as response: response.read()
        status="completed"
    except Exception as error: status=type(error).__name__
    return {"sentence":sentence,"model_elapsed_s":round(time.perf_counter()-start,3),"status":status}
for sentence in cases[:2]: print(json.dumps(model_probe(sentence),ensure_ascii=False))
