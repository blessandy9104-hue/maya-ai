import json,sys
from urllib.parse import urlparse
p="evolution/network_policy.json"
x=json.load(open(p))
raw=sys.argv[1] if len(sys.argv)>1 else ""
host=urlparse(raw if "://" in raw else "https://"+raw ).hostname
if not host or "." not in host: raise SystemExit("Invalid domain")
if host not in x["allowed_hosts"]: x["allowed_hosts"].append(host)
open(p,"w").write(json.dumps(x,indent=2))
print("Allowed read-only host:",host)
