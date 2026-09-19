"""Free, explicit, read-only general web search for Maya."""
from __future__ import annotations

import base64
import html
import ipaddress
import json
import re
import socket
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "evolution" / "network_policy.json"
LOG = ROOT / "knowledge" / "web_search_notes.jsonl"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(" ".join(data.split()))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _policy():
    try:
        return json.loads(POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _public_https(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.port not in (None, 443):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
    except (OSError, ValueError):
        return False
    return True


def _search(query: str, limit: int):
    policy = _policy()
    if policy.get("enabled") is not True or policy.get("mode") != "read_only":
        return []
    search_host = "www.bing.com"
    if search_host not in policy.get("search_hosts", []):
        return []
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    search_timeout = max(20, int(policy.get("timeout_seconds", 10)))
    timeout = str(search_timeout)
    result = subprocess.run(
        ["curl", "-L", "--max-time", timeout, "-A", "Maya-Local-Research/1.0", "-sS", url],
        capture_output=True, timeout=search_timeout + 5,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "search request failed")
    raw = result.stdout[:min(int(policy.get("max_bytes", 200000)), 500000)]
    raw_text = raw.decode("utf-8", "replace")
    result_pattern = re.compile(
        r'<li[^>]+class=["\'][^"\']*b_algo[^"\']*["\'][^>]*>.*?'
        r'<h2[^>]*><a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>.*?'
        r'<p[^>]*>(.*?)</p>.*?</li>',
        re.IGNORECASE | re.DOTALL,
    )
    results = []
    terms = [term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2]
    for match in result_pattern.finditer(raw_text):
        href, title_html, snippet_html = match.groups()
        if not href:
            continue
        href = html.unescape(href)
        parsed = urllib.parse.urlparse(href)
        if parsed.netloc in {"www.bing.com", "bing.com"} and parsed.path.startswith("/ck/"):
            params = urllib.parse.parse_qs(parsed.query)
            encoded = params.get("u", [""])[0]
            if encoded.startswith("a1"):
                try:
                    padded = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
                    href = base64.urlsafe_b64decode(padded).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    continue
        if not _public_https(href):
            continue
        title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", title_html)).split())
        snippet_text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", snippet_html)).split())[:500]
        haystack = (title + " " + snippet_text).lower()
        score = sum(1 for term in terms if term in haystack)
        results.append({
            "title": title,
            "url": href,
            "snippet": snippet_text,
            "score": score,
            "partial_match": bool(terms and score < len(terms)),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    if terms:
        complete = [item for item in results if not item["partial_match"]]
        if complete:
            return complete[:limit]
        wiki_results = _wiki_search(query, limit)
        if wiki_results:
            return wiki_results
    return results[:limit]


def _wiki_search(query: str, limit: int):
    policy = _policy()
    if "en.wikipedia.org" not in policy.get("allowed_hosts", []):
        return []
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": query,
        "format": "json", "utf8": "1", "srlimit": str(limit),
    })
    result = subprocess.run(
        ["curl", "-L", "--max-time", str(int(policy.get("timeout_seconds", 10))),
         "-A", "Maya-Local-Research/1.0", "-sS", url],
        capture_output=True, timeout=int(policy.get("timeout_seconds", 10)) + 5,
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return []
    results = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "").strip()
        if not title:
            continue
        page_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        snippet = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", item.get("snippet", ""))).split())
        noise = re.search(r"\b(song|album|film|movie|tv series|television series|video game|disambiguation|store|company)\b", (title + " " + snippet).lower())
        if noise:
            continue
        results.append({
            "title": title + " - Wikipedia",
            "url": page_url,
            "snippet": snippet,
            "score": len(re.findall(r"[a-z0-9]+", query.lower())),
            "partial_match": False,
        })
    return results[:limit]


def _fetch(url: str):
    policy = _policy()
    request = urllib.request.Request(url, headers={"User-Agent": "Maya-Local-Research/1.0"})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(request, timeout=int(policy.get("timeout_seconds", 10))) as response:
        raw = response.read(min(int(policy.get("max_bytes", 200000)), 300000))
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", "replace"))
    text = " ".join(parser.parts)
    return text[:2500]


def answer_web(query: str, limit: int = 3, show_sources: bool = False) -> str:
    query = " ".join(query.split()).strip()
    if not query:
        return "Tell me what you want me to look up."
    try:
        results = _search(query, max(1, min(limit, 5)))
    except Exception as error:
        return f"I could not search the web right now: {error}"
    if not results:
        return "I could not find usable public HTTPS results for that question."
    sections = []
    for item in results:
        text = item.get("snippet", "").strip()
        if text:
            sections.append(f"{item['title']}: {text[:400]}")


    if not sections:
        return "I found results, but their pages were not readable right now."
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "timestamp": _now(), "query": query,
            "sources": [{"title": x["title"], "url": x["url"]} for x in results],
            "memory_update": "not_performed",
        }, ensure_ascii=False) + "\n")
    answer = "\n\n".join(sections)
    if any(item.get("partial_match") for item in results):
        answer = "The search engine returned partial matches, so treat this answer as lower-confidence and ask me to refine the topic if needed.\n\n" + answer
    if show_sources:
        answer += "\n\nSources:\n" + "\n".join(f"- {x['title']}: {x['url']}" for x in results)
    return answer


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 maya_web_search.py QUESTION [--sources]")
        raise SystemExit(2)
    args = sys.argv[1:]
    show_sources = "--sources" in args
    args = [arg for arg in args if arg != "--sources"]
    print(answer_web(" ".join(args), show_sources=show_sources))
