import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
policy_path = ROOT / "evolution" / "network_policy.json"
p = json.loads(policy_path.read_text(encoding="utf-8"))
u = sys.argv[1] if len(sys.argv) > 1 else ""
z = urlparse(u)
if (
    p.get("enabled") is not True
    or p.get("mode") != "read_only"
    or z.scheme != "https"
    or z.hostname not in p.get("allowed_hosts", [])
):
    raise SystemExit("Blocked: host, scheme, or network mode is not allowed")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

req = urllib.request.Request(
    u,
    headers={"User-Agent": "Maya-Local-ReadOnly/1.0"},
    method="GET",
)
opener = urllib.request.build_opener(NoRedirect)
with opener.open(req, timeout=int(p.get("timeout_seconds", 10))) as response:
    data = response.read(int(p.get("max_bytes", 200000)) + 1)
if len(data) > int(p.get("max_bytes", 200000)):
    raise SystemExit("Blocked: response too large")

log = {"url": u, "host": z.hostname, "bytes": len(data), "mode": "read_only"}
log_path = ROOT / "evolution" / "network_log.jsonl"
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(log) + "\n")
print(data.decode("utf-8", "replace"))
