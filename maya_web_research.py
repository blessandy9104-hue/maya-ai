import html, ipaddress, json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import maya_service

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "knowledge" / "research_cache.jsonl"
CACHE_TTL_DAYS = 30
CACHE_MAX_ENTRIES = 500
CACHE_MAX_BYTES = 2 * 1024 * 1024
POLICY = ROOT / "evolution" / "network_policy.json"

_TAG_RE = re.compile(r"<(?:\"[^\"]*\"|'[^']*'|[^>\"'])*>", flags=re.S)

HOST_CLASSES = {
    "en.wikipedia.org": "encyclopedic",
    "plato.stanford.edu": "scholarly",
    "iep.utm.edu": "scholarly",
    "docs.python.org": "technical",
    "api.github.com": "technical",
}

CLASS_WEIGHTS = {
    "scholarly": 0.85,
    "institutional": 0.85,
    "technical": 0.85,
    "encyclopedic": 0.60,
    "general": 0.35,
}

CLASS_CAPS = {
    "encyclopedic": 2,
    "scholarly": 2,
    "technical": 2,
    "institutional": 1,
    "general": 0,
}

PHILOSOPHY_TERMS = (
    "philosophy", "philosopher", "philosophical", "ethics", "ethical",
    "nietzsche", "kant", "plato", "aristotle", "jung", "epistemology",
    "metaphysics", "consciousness", "existential", "existentialism",
    "phenomenology", "stoic", "stoicism", "logic", "ontology", "aesthetics",
)

TECHNICAL_TERMS = (
    "python", "api", "github", "function", "library", "module", "framework",
    "bash", "linux", "command", "code", "programming", "sdk", "documentation",
    "requests", "endpoint", "http", "json", "sql", "docker",
)

TIER_BELIEF = {"low": 0.35, "medium": 0.60, "high": 0.85}
TIERS = frozenset(TIER_BELIEF)


_SINGULAR_EXCEPTIONS = frozenset((
    "analysis", "apparatus", "atlas", "basis", "bias", "bus", "business",
    "campus", "canvas", "chaos", "class", "consensus", "cosmos", "crisis",
    "ethics", "gas", "glass", "grass", "hiatus", "iris", "itis", "lens",
    "mass", "means", "news", "parenthesis", "physics", "police", "press",
    "process", "series", "species", "status", "thesis", "this", "zero",
))

_SINGULAR_MAP = {
    "children": "child", "feet": "foot", "geese": "goose", "men": "man",
    "mice": "mouse", "people": "person", "teeth": "tooth", "women": "woman",
}


def _singularize(word):
    if word in _SINGULAR_EXCEPTIONS or len(word) <= 3:
        return word
    if word in _SINGULAR_MAP:
        return _SINGULAR_MAP[word]
    if word.endswith("ies") and word[-4] not in "aeiou":
        return word[:-3] + "y"
    if word.endswith("es") and (word.endswith(("ches", "shes")) or word[-3] in "sxz"):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def _normalize_topic(topic):
    return " ".join(_singularize(word) for word in topic.lower().split())


def _read_cache():
    if not CACHE_FILE.exists():
        return []
    entries = []
    try:
        for line in CACHE_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if isinstance(entry, dict) and entry.get("topic"):
                entries.append(entry)
    except Exception:
        return []
    return entries


def _cache_hit(topic):
    key = _normalize_topic(topic)
    now = datetime.now(timezone.utc)
    for entry in _read_cache():
        if _normalize_topic(entry.get("topic", "")) != key:
            continue
        try:
            retrieved = datetime.fromisoformat(entry["retrieved_at"])
        except Exception:
            continue
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
        if now - retrieved <= timedelta(days=CACHE_TTL_DAYS):
            return entry
    return None


def _render_cached(entry, topic):
    meta = entry.get("meta") or {}
    rows = [_normalize_evidence(row) for row in (entry.get("sources") or [])]
    meta["source_notes"] = entry.get("source_notes") or meta.get("source_notes") or []
    meta["retrieved_at"] = entry.get("retrieved_at", "")
    return research_summary(topic, rows, meta)


# ----------------------------------------------------------------------
# Research-cache persistence. Outcomes are three-state (never a bare bool)
# so a silent skip can never masquerade as a failure, or vice versa:
#   WRITTEN                  - entry atomically persisted
#   SKIPPED_SERVICE_OFFLINE  - intentionally suppressed: offline/background
#                              test or local scripted run with no live service
#   FAILED                   - an exception occurred while writing (logged)
# The documented intent (see _persist_research_disagreements) is that
# "offline tests and local scripted runs never write". Genuine interactive
# console/Qt/Tk requests must persist even when the presence service happens
# to be asleep; only offline tests and local scripted runs are suppressed.
# ----------------------------------------------------------------------

PERSIST_WRITTEN = "WRITTEN"
PERSIST_SKIPPED = "SKIPPED_SERVICE_OFFLINE"
PERSIST_FAILED = "FAILED"

_USER_FACING_ENV = os.environ.get("MAYA_USER_FACING", "").strip().lower()
_SUPPRESS_ENV = os.environ.get("MAYA_SUPPRESS_WRITES", "").strip().lower()


def _offline_invocation():
    """True when this process is an offline test or local scripted run.

    Suppression matches the documented intent: pytest/unittest runners, test
    modules (test_*.py), and ``-c``/``-m`` scripted invocations never write
    the research cache. Everything else - the console app (maya_chat.py), the
    Qt bridge, the Tk app, and standalone user tools - counts as a genuine
    user-facing process and may persist without service liveness.
    Environment overrides for automation: MAYA_USER_FACING=1 forces
    user-facing mode; MAYA_SUPPRESS_WRITES=1 forces suppression.
    """
    if _SUPPRESS_ENV in ("1", "true", "yes", "on"):
        return True
    if _USER_FACING_ENV in ("1", "true", "yes", "on"):
        return False
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 in ("-c", ""):
        return True
    stem = Path(argv0).stem.lower()
    if stem.startswith("test_"):
        return True
    for mod in list(sys.modules):
        if mod == "pytest" or mod.startswith("pytest."):
            return True
        if mod == "unittest" or mod.startswith("unittest."):
            return True
    main = sys.modules.get("__main__")
    main_name = getattr(main, "__name__", "")
    if main_name.startswith("test_"):
        return True
    return False


def _persist_log(line):
    """Append a persistence-outcome line to the service log (best-effort)."""
    try:
        maya_service.LOG.parent.mkdir(parents=True, exist_ok=True)
        with maya_service.LOG.open("a", encoding="utf-8") as handle:
            handle.write("[%s] %s\n" % (datetime.now(timezone.utc).isoformat(), line))
    except Exception:
        pass


def _json_safe(value):
    """Recursively normalize non-JSON types (sets -> sorted lists) so cache
    entries always serialize. Stops set-from-policy values such as
    meta["allowed_hosts"] from silently killing the whole write."""
    if isinstance(value, set):
        return sorted(value, key=lambda x: str(x))
    if isinstance(value, dict):
        return {_json_safe(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_cache(topic, retrieved_at, source_notes, rows, meta):
    try:
        pid = maya_service.running_pid()
    except Exception:
        pid = None
    if not pid and _offline_invocation():
        return PERSIST_SKIPPED
    key = _normalize_topic(topic)
    entry = {
        "topic": topic,
        "retrieved_at": retrieved_at,
        "source_notes": source_notes,
        "meta": meta,
        "sources": rows,
        "unreviewed_cache": True,
    }
    try:
        existing = _read_cache()
        kept = [e for e in existing if _normalize_topic(e.get("topic", "")) != key]
        kept.append(entry)
        if len(kept) > CACHE_MAX_ENTRIES:
            kept = kept[-CACHE_MAX_ENTRIES:]
        lines = [json.dumps(_json_safe(e), ensure_ascii=False) for e in kept]
        text = "\n".join(lines) + "\n" if lines else ""
        while len(text.encode("utf-8")) > CACHE_MAX_BYTES and len(lines) > 1:
            lines.pop(0)
            text = "\n".join(lines) + "\n"
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".jsonl.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(CACHE_FILE))
        return PERSIST_WRITTEN
    except Exception as exc:
        _persist_log("_write_cache FAILED for topic '%s': %r" % (topic, exc))
        return PERSIST_FAILED


def safe(url):
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in ('http', 'https') or p.username or p.password:
            return False
        host = p.hostname or ''
        if host in ('localhost', '127.0.0.1', '::1'):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass
        return bool(host)
    except Exception:
        return False

def text_only(raw):
    raw = re.sub(r'<script[^>]*>.*?</script>|<style[^>]*>.*?</style>', ' ', raw, flags=re.I|re.S)
    return re.sub(r'\s+', ' ', _TAG_RE.sub(' ', raw)).strip()

def _public_fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'Maya-public-research/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode('utf-8', 'replace')


def host_class(host):
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return HOST_CLASSES.get(host, "general")


def topic_terms(topic):
    return [word for word in re.findall(r"[a-z0-9]+", topic.lower()) if len(word) >= 3]


def _clean_wiki_markup(text):
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\[\s*[0-9]+\s*\]", " ", text)
    text = re.sub(r"&lt;ref[^&]*&gt;|&lt;/?ref[^&]*&gt;|</?ref[^>]*>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.I | re.S)
    return re.sub(r"\s+", " ", text).strip()


def _first_sentence(text):
    cleaned = _clean_wiki_markup(text)
    parts = re.split(r'(?<=[.!?])\s+', cleaned.strip())
    if not parts or not parts[0].strip():
        return ""
    first = parts[0].strip()
    if not first.rstrip().endswith(('.', '!', '?')):
        first += "."
    return first


# ----------------------------------------------------------------------
# Evidence-quality gate. Deterministic and conservative: it rejects only
# explicit contentless retrieval artifacts (list/index leads,
# disambiguation shells, stub/maintenance boilerplate, and near-empty
# descriptive leads). It NEVER judges quality by length, source class, or
# topic-keyword overlap, so short but informative content survives and
# sources that omit many query terms are unaffected.
# ----------------------------------------------------------------------

STUB_LIST_LEAD = "stub_list_lead"
DISAMBIGUATION_LEAD = "disambiguation_lead"
STUB_BOILERPLATE = "stub_boilerplate"
NON_INFORMATIVE_LEAD = "non_informative_lead"

_LIST_LEAD_MARKERS = (
    "this is a list of",
    "the following is a list of",
    "below is a list of",
    "this article is a list of",
    "this page is a list of",
    "the following is a partial list of",
    "this is a partial list of",
    "below is a partial list of",
    "this is an index of",
    "the following is an index of",
    "this is an alphabetical list of",
    "this is a chronological list of",
    "this is a complete list of",
    "this is a bibliography of",
    "this is a discography of",
    "the following is a bibliography of",
)

_DISAMBIGUATION_MARKERS = (
    "may refer to",
    "is a disambiguation",
    "disambiguation page",
    "disambiguation pages",
)

_STUB_BOILERPLATE_MARKERS = (
    "is a stub",
    "stub article",
    "this article does not cite any sources",
    "this article needs additional citations",
    "you can help by expanding it",
    "this article relies largely or entirely on a single source",
    "the topic of this article may not meet",
)

_BOILERPLATE_OPENERS = (
    "this is a",
    "this is an",
    "this article is a",
    "this article is an",
    "this page is a",
    "this page is an",
    "the following is a",
    "the following is an",
)

_NON_INFORMATIVE_CONTINUATIONS = (
    "about", "of", "on", "in", "for", "including",
    "such as", "that", "which", "who", "with", "by", "known as",
)


def evidence_gate_decision(snippet):
    """Deterministic evidence-quality predicate for one retrieved excerpt.

    Returns ``("ACCEPT", None)`` or ``("REJECT", <reason_code>)``. Pure
    function: no network, no model, no filesystem access. The reason codes
    are ``stub_list_lead``, ``disambiguation_lead``, ``stub_boilerplate``,
    and ``non_informative_lead``.
    """
    text = _clean_wiki_markup(str(snippet or "")).strip()
    if not text:
        return ("REJECT", NON_INFORMATIVE_LEAD)
    condensed = re.sub(r"[^a-z0-9\s]+", " ", text.lower())
    condensed = " ".join(condensed.split())
    words = condensed.split()
    if any(marker in condensed for marker in _LIST_LEAD_MARKERS):
        return ("REJECT", STUB_LIST_LEAD)
    if any(marker in condensed for marker in _DISAMBIGUATION_MARKERS):
        return ("REJECT", DISAMBIGUATION_LEAD)
    if any(marker in condensed for marker in _STUB_BOILERPLATE_MARKERS):
        return ("REJECT", STUB_BOILERPLATE)
    for opener in _BOILERPLATE_OPENERS:
        if condensed.startswith(opener):
            rest = words[len(opener.split()):]
            rest_text = " ".join(rest)
            if not rest_text:
                return ("REJECT", NON_INFORMATIVE_LEAD)
            if len(rest) < 3 and not any(
                    re.search(r"\b" + re.escape(marker) + r"\b", rest_text)
                    for marker in _NON_INFORMATIVE_CONTINUATIONS):
                return ("REJECT", NON_INFORMATIVE_LEAD)
            break
    return ("ACCEPT", None)


def _filtered_note(filtered):
    shown = filtered[:3]
    items = ["%s (%s)" % ((url or "?")[:80], reason)
             for url, reason in shown]
    extra = len(filtered) - len(shown)
    if extra > 0:
        items.append("%d more" % extra)
    return ("Evidence filtering note: %d contentless retrieval artifact "
            "snippet(s) excluded from evidence (%s)."
            % (len(filtered), ", ".join(items)))


def score_relevance(topic, title, snippet):
    terms = topic_terms(topic)
    if not terms:
        return 1.0
    hay = ((title or "") + " " + (snippet or "")).lower()
    present = sum(1 for term in terms if term in hay)
    base = present / len(terms)
    bonus = 0.15 * (len(terms) - present) / len(terms)
    return round(min(1.0, base + bonus), 2)


def accept_relevance(score, present, total):
    if total <= 0:
        return True
    return present >= total or score >= 0.6


def tier_for(source_class, relevance):
    base = CLASS_WEIGHTS.get(source_class, 0.35)
    if relevance >= 0.85:
        base = min(1.0, base + 0.15)
    elif relevance < 0.55:
        base = max(0.25, base - 0.15)
    if base >= 0.75:
        return "high", TIER_BELIEF["high"]
    if base >= 0.50:
        return "medium", TIER_BELIEF["medium"]
    return "low", TIER_BELIEF["low"]


def _normalize_url(url):
    url = html.unescape(urllib.parse.unquote(url)).strip()
    url = url.split("#", 1)[0]
    url = url.split("?", 1)[0]
    url = url.rstrip("/")
    if url.startswith("https://en.wikipedia.org/wiki/"):
        url = "https://en.wikipedia.org/wiki/" + url[len("https://en.wikipedia.org/wiki/"):].replace("_", " ")
    if url.startswith("http://en.wikipedia.org/wiki/"):
        url = "https://en.wikipedia.org/wiki/" + url[len("http://en.wikipedia.org/wiki/"):].replace("_", " ")
    return url.lower()


def dedupe_candidates(candidates):
    seen_urls = set()
    seen_titles = set()
    out = []
    for candidate in candidates:
        url = candidate.get("url") or ""
        normalized = _normalize_url(url)
        if normalized not in seen_urls:
            seen_urls.add(normalized)
        else:
            continue
        title = re.sub(r"[^a-z0-9]+", "", (candidate.get("title") or "").lower())
        if title and title in seen_titles:
            continue
        if title:
            seen_titles.add(title)
        out.append(candidate)
    return out


def classify_query(topic):
    kind = "statement_or_general_request"
    confidence = 0.5
    try:
        from maya_intent_cues import classify_opening
        cue = classify_opening(topic)
        kind = cue["primary_intent"]
        confidence = float(cue["confidence"])
        if confidence > 1.0:
            confidence = round(confidence / 100.0, 2)
    except Exception:
        pass
    lowered = topic.lower()
    classes = ["encyclopedic"]
    philosophical = any(term in lowered for term in PHILOSOPHY_TERMS)
    technical = any(term in lowered for term in TECHNICAL_TERMS)
    if kind in ("reason_or_cause", "process_or_explanation", "request_for_explanation", "definition_or_information"):
        classes.append("scholarly")
    if philosophical:
        classes.append("scholarly")
    if technical:
        classes.append("technical")
    seen = []
    for value in classes:
        if value not in seen:
            seen.append(value)
    return {"kind": kind, "confidence": round(confidence, 2), "classes": seen}


def _policy_state():
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "ok", None
    if policy.get("enabled") is not True or policy.get("mode") != "read_only":
        return "paused", set()
    allowed = set(policy.get("allowed_hosts") or [])
    return "ok", allowed


def _add_link(links, url):
    url = html.unescape(urllib.parse.unquote(url)).strip()
    if url.startswith('/'):
        return
    if 'uddg=' in url:
        url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('uddg', [url])[0]
    host = urllib.parse.urlparse(url).netloc.lower()
    blocked = ('bing.com', 'microsoft.com', 'duckduckgo.com', 'r.bing.com', 'th.bing.com')
    if url.startswith(('http://', 'https://')) and host and not any(x in host for x in blocked) and safe(url) and url not in links:
        links.append(url)


def _clean_page_text(raw):
    raw = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', raw, flags=re.I | re.S)
    raw = _TAG_RE.sub(' ', raw)
    raw = html.unescape(raw)
    return re.sub(r'\s+', ' ', raw).strip()


def _answer_summary(raw):
    """Return only a few relevant, readable sentences from a public page."""
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', raw, flags=re.I | re.S)
    cleaned = []
    for paragraph in paragraphs:
        text = _clean_page_text(paragraph)
        if len(text) >= 80 and text not in cleaned:
            first = re.split(r'(?<=[.!?])\s+', text, maxsplit=1)[0].strip()
            if len(first) >= 45:
                cleaned.append(first)
    if cleaned:
        return ' '.join(cleaned[:2])[:500]
    text = _clean_page_text(raw)
    return re.split(r'(?<=[.!?])\s+', text, maxsplit=1)[0][:500]


def _topic_matches(body, topic):
    words = [word.lower() for word in re.findall(r"[a-zA-Z0-9]+", topic) if len(word) >= 3]
    lowered = body.lower()
    return bool(words) and all(word in lowered for word in words)


def _wiki_search_candidates(topic):
    candidates = []
    api = ('https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch='
           + urllib.parse.quote(topic) + '&format=json&utf8=1&srlimit=5')
    data = json.loads(_public_fetch(api))
    for item in data.get('query', {}).get('search', []):
        title = item.get('title', '')
        if not title:
            continue
        url = 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_'))
        candidates.append({"url": url, "title": title + ' - Wikipedia', "host": "en.wikipedia.org", "class": "encyclopedic"})
    return candidates


def _rss_candidates(query):
    candidates = []
    rss = _public_fetch('https://www.bing.com/search?format=rss&q=' + urllib.parse.quote(query))
    for block in re.findall(r'<item>(.*?)</item>', rss, re.I | re.S):
        link_match = re.search(r'<link>\s*(https?://[^<]+?)\s*</link>', block, re.I)
        if not link_match:
            continue
        url = link_match.group(1).strip()
        if not safe(url) or not url.startswith(('http://', 'https://')):
            continue
        host = urllib.parse.urlparse(url).netloc.lower()
        title_match = re.search(r'<title>\s*(.*?)\s*</title>', block, re.I | re.S)
        title = html.unescape(re.sub(r'<[^>]+>', ' ', title_match.group(1))).strip() if title_match else host
        candidates.append({"url": url, "title": title, "host": host, "class": host_class(host)})
    return candidates


def _ddg_candidates(query):
    candidates = []
    page = _public_fetch('https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query))
    for block in re.findall(r'class=["\']result__a["\'][^>]*', page, re.I):
        href = re.search(r'href=["\']([^"\']+)', block)
        if not href:
            continue
        url = html.unescape(urllib.parse.unquote(href.group(1))).strip()
        if 'uddg=' in url:
            url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('uddg', [url])[0]
        if not safe(url) or not url.startswith(('http://', 'https://')):
            continue
        host = urllib.parse.urlparse(url).netloc.lower()
        candidates.append({"url": url, "title": host, "host": host, "class": host_class(host)})
    return candidates


def _discover_candidates(topic, allowed, query_meta):
    candidates = []
    source_notes = []
    if allowed is None or "en.wikipedia.org" in allowed:
        try:
            added = _wiki_search_candidates(topic)
            if added:
                candidates.extend(added)
                source_notes.append('Wikipedia API')
        except Exception:
            pass
    scholarly_hosts = [host for host in ("plato.stanford.edu", "iep.utm.edu")
                       if (allowed is None or host in allowed) and "scholarly" in query_meta.get("classes", [])]
    technical_hosts = [host for host in ("docs.python.org", "api.github.com")
                       if (allowed is None or host in allowed) and "technical" in query_meta.get("classes", [])]
    queries = [topic]
    queries.extend("site:%s %s" % (host, topic) for host in scholarly_hosts + technical_hosts)
    try:
        any_rss = False
        for query in queries[:3]:
            for candidate in _rss_candidates(query):
                if allowed is None or candidate["host"] in allowed:
                    candidates.append(candidate)
                    any_rss = True
        if any_rss:
            source_notes.append('Bing RSS')
    except Exception:
        pass
    try:
        any_ddg = False
        for candidate in _ddg_candidates(topic):
            if allowed is None or candidate["host"] in allowed:
                candidates.append(candidate)
                any_ddg = True
        if any_ddg:
            source_notes.append('DuckDuckGo HTML')
    except Exception:
        pass
    return candidates, list(dict.fromkeys(source_notes))


def plan_candidates(topic, candidates, query_meta, allowed=None, caps=None):
    caps = caps or CLASS_CAPS
    scored = []
    for candidate in candidates:
        cand_class = candidate.get("class") or host_class(candidate.get("host", ""))
        candidate = dict(candidate)
        candidate["class"] = cand_class
        relevance = score_relevance(topic, candidate.get("title", ""), "")
        score = relevance
        if cand_class in query_meta.get("classes", []):
            score += 0.1
        scored.append({"candidate": candidate, "score": score, "relevance": relevance})
    scored.sort(key=lambda item: item["score"], reverse=True)
    selected = []
    counts = {}
    for entry in scored:
        candidate = entry["candidate"]
        cand_class = candidate.get("class", "general")
        if cand_class == "general":
            continue
        if allowed is not None and candidate.get("host") not in allowed:
            continue
        if counts.get(cand_class, 0) >= caps.get(cand_class, 2):
            continue
        selected.append(candidate)
        counts[cand_class] = counts.get(cand_class, 0) + 1
        if len(selected) >= 6:
            break
    return selected


def _accept_evidence(topic, title, snippet):
    if not snippet:
        return False
    relevance = score_relevance(topic, title, snippet)
    terms = topic_terms(topic)
    hay = ((title or "") + " " + snippet).lower()
    present = sum(1 for term in terms if term in hay)
    return accept_relevance(relevance, present, len(terms))


def _normalize_evidence(row):
    row = dict(row or {})
    url = row.get("url", "")
    host = row.get("host") or (urllib.parse.urlparse(url).netloc.lower() if url else "")
    cand_class = row.get("class") or host_class(host)
    relevance = row.get("relevance")
    tier = row.get("tier")
    belief = row.get("belief")
    if tier not in TIERS or belief not in TIER_BELIEF.values():
        tier, belief = tier_for(cand_class, relevance if relevance is not None else 1.0)
    row.setdefault("host", host)
    row.setdefault("class", cand_class)
    row["tier"] = tier
    row["belief"] = belief
    row.setdefault("snippet", "")
    row.setdefault("title", host)
    return row


def _detect_contradictions(rows):
    pairs = []
    try:
        from maya_math.evidence import analyze_evidence
        members = []
        for index, row in enumerate(rows):
            claim = _first_sentence(row.get("snippet", ""))
            if not claim:
                continue
            members.append({
                "evidence_id": "e%d" % index,
                "claim": claim,
                "source": row.get("url", ""),
                "confidence": row.get("tier", "medium"),
                "uncertainty": round(max(0.0, 1.0 - float(row.get("relevance", 0.6))), 3),
            })
        if members:
            analysis = analyze_evidence(members, min_overlap=2)
            for entry in analysis.get("contradictions", []):
                pairs.append({
                    "index_a": entry.get("claim_a"),
                    "index_b": entry.get("claim_b"),
                    "basis": entry.get("basis"),
                })
    except Exception:
        pass
    return pairs


def _entropy_report(rows):
    try:
        from maya_math.evidence import analyze_evidence
        members = []
        for index, row in enumerate(rows):
            claim = _first_sentence(row.get("snippet", ""))
            if not claim:
                continue
            members.append({
                "evidence_id": "e%d" % index,
                "claim": claim,
                "source": row.get("url", ""),
                "confidence": row.get("tier", "medium"),
                "uncertainty": round(max(0.0, 1.0 - float(row.get("relevance", 0.6))), 3),
            })
        if members:
            analysis = analyze_evidence(members, min_overlap=2)
            belief = analysis.get("belief") or {}
            return {
                "items": int(belief.get("items", 0)),
                "entropy_bits": float(belief.get("entropy_bits", 0.0)),
                "normalized_entropy": float(belief.get("normalized_entropy", 0.0)),
            }
    except Exception:
        pass
    return None


def combine_confidences(rows):
    implicated = set(_implicated_indexes(rows))
    agreeing = [float(row.get("belief", 0.35)) for i, row in enumerate(rows)
                if i not in implicated]
    conflicting = [float(row.get("belief", 0.35)) for i, row in enumerate(rows)
                   if i in implicated]
    try:
        from maya_math.probability import combine_confidences as _combine
        value = _combine(agreeing, conflicting)
    except Exception:
        value = max(agreeing) if agreeing else (min(conflicting) if conflicting else 0.0)
    if value >= 0.7:
        return "high", round(value, 2)
    if value >= 0.5:
        return "medium", round(value, 2)
    return "low", round(value, 2)


def _implicated_indexes(rows):
    implicated = set()
    for index_a, row_a in enumerate(rows):
        for index_b, row_b in enumerate(rows):
            if index_a >= index_b:
                continue
            try:
                from maya_math.logic import contradictory_claims
                result = contradictory_claims(
                    _first_sentence(row_a.get("snippet", "")),
                    _first_sentence(row_b.get("snippet", "")),
                    min_overlap=2)
                flagged = result.get("contradictory", False)
            except Exception:
                flagged = False
            if flagged:
                implicated.add(index_a)
                implicated.add(index_b)
    return sorted(implicated)


def _evidence_status(rows, contradiction_pairs, reason):
    if not rows:
        return "unknown"
    if contradiction_pairs:
        return "disputed"
    if len(rows) == 1:
        return "supported (limited)"
    return "supported"


def extract_summary_evidence(topic, summary_text=None):
    """Owner-side recovery of (rows, meta, analysis) from one research answer.

    Prefers the research cache (structured rows, full metadata). Falls back
    to parsing the rendered summary — the same text every consumer sees —
    so live-fetch and cache-replay paths are tagged identically. Returns
    ``rows=[]`` when nothing usable is present.
    """
    rows, meta = [], {}
    try:
        cached = _cache_hit(topic)
        if cached is not None:
            rows = [dict(row) for row in (cached.get("sources") or [])]
            meta = dict(cached.get("meta") or {})
            meta["retrieved_at"] = cached.get("retrieved_at", "")
        else:
            text = str(summary_text or "")
            if "Evidence:" in text and "1. Source:" in text:
                block = text.split("Evidence:", 1)[1].split("\nDifferences:", 1)[0]
                for chunk in re.split(r"\n(?=\d+\. Source: )", block.strip()):
                    url = title = snippet = ""
                    for line in chunk.splitlines():
                        line = line.strip()
                        url_match = re.match(r"(?:\d+\.)?\s*Source: (.*)", line)
                        if url_match:
                            url = url_match.group(1).strip()
                        elif line.startswith("Supports: "):
                            snippet = line[len("Supports: "):].strip()
                    if url or snippet:
                        rows.append({"url": url, "title": title, "snippet": snippet})
                # Normalize parsed rows through the same normalizer the
                # rendered summary used, so class/tier/belief and the
                # answer-level verdict match the answer text exactly.
                rows = [_normalize_evidence(row) for row in rows]
                retrieved = ""
                for line in text.splitlines():
                    if line.startswith("Evidence retrieved: "):
                        retrieved = line[len("Evidence retrieved: "):].strip()
                # The summary renders the ISO timestamp truncated to seconds
                # plus " UTC"; normalize back to a Z-suffixed ISO form.
                if retrieved.endswith(" UTC"):
                    retrieved = retrieved[:-4]
                if retrieved and not retrieved.endswith("Z"):
                    retrieved += "Z"
                if retrieved:
                    meta["retrieved_at"] = retrieved
    except Exception:
        return [], {}, None
    if not rows:
        return [], {}, None
    try:
        analysis = analyze_rows(rows)
    except Exception:
        analysis = None
    return rows, meta, analysis


def research_summary(topic, rows, meta=None):
    meta = dict(meta or {})
    rows = [_normalize_evidence(row) for row in rows]
    # Evidence-quality gate: clearly contentless retrieval artifacts are
    # excluded before they can be rendered as evidence. Callers may also
    # report rejections they already dropped via meta["filtered"]; both are
    # merged (deduplicated) into one deterministic note.
    meta_filtered = [tuple(item) for item in (meta.get("filtered") or [])]
    accepted, self_filtered = [], []
    for row in rows:
        decision, reason = evidence_gate_decision(row.get("snippet", ""))
        if decision == "REJECT":
            self_filtered.append((row.get("url", ""), reason))
        else:
            accepted.append(row)
    rows = accepted
    filtered = []
    for item in meta_filtered + self_filtered:
        if item not in filtered:
            filtered.append(item)
    allowed = meta.get("allowed_hosts")

    notes = meta.get("source_notes") or []
    lines = [
        f"Brief research summary: {topic}",
        "Read-only research. Relevant points only; no trusted-memory update occurred.",
        "Sources discovered: " + (", ".join(notes) if notes else "no allowed sources"),
        "Query class: %s (classification confidence %s)"
        % (meta.get("kind", "statement_or_general_request"),
           "%.2f" % float(meta.get("kind_confidence", 0.0))),
    ]
    if meta.get("retrieved_at"):
        lines.append("Evidence retrieved: " + str(meta["retrieved_at"])[:19] + " UTC")

    if not rows:
        lines.append("\nNo evidence from any allowed source class could be retrieved.")
        if filtered:
            lines.append("\n" + _filtered_note(filtered))
        lines.append("\nStatus: unknown")
        lines.append("Confidence: low (no retrieved evidence)")
        lines.append("\nNo trusted memory update occurred.")
        return "\n".join(lines)

    ordered = sorted(rows, key=lambda row: (float(row.get("belief", 0.0)),
                                            float(row.get("relevance", 0.0))), reverse=True)

    core_parts = [_first_sentence(ordered[0].get("snippet", ""))]
    if len(ordered) > 1 and ordered[1].get("class") != ordered[0].get("class"):
        second = _first_sentence(ordered[1].get("snippet", ""))
        if second:
            core_parts.append(second)
    lines.append("\nCore understanding (synthesized from %d source(s)):\n%s"
                 % (len(rows), "\n".join(part for part in core_parts if part) or "No usable core text extracted."))

    lines.append("\nEvidence:")
    for index, row in enumerate(ordered, start=1):
        lines.append("%d. Source: %s" % (index, row.get("url", "")))
        lines.append("   Type: %s" % row.get("class", "general"))
        lines.append("   Confidence: %s" % row.get("tier", "medium"))
        supports = _clean_wiki_markup(row.get("snippet", ""))
        lines.append("   Supports: " + (" ".join(supports.split())[:420] or "No readable excerpt."))

    baseline = _world_baseline(topic)
    if baseline:
        lines.append("\nKnown world baseline (neutral stored evidence, review-only):")
        for entry in baseline:
            lines.append("- Claim: %s"
                         % _clean_wiki_markup(str(entry.get("claim", "")))[:260] or "- Claim: (empty)")
            lines.append("  Source: %s | confidence: %s | conflict: %s | retrieved: %s"
                         % (str(entry.get("source") or "?"),
                            str(entry.get("confidence") or "?"),
                            str(entry.get("conflict_status") or "no_conflict_detected"),
                            str(entry.get("retrieved_at") or "")[:19]))

    contradiction_pairs = _detect_contradictions(rows)
    reason = _confidence_reason(rows, contradiction_pairs)
    label, value = combine_confidences(rows)
    status = _evidence_status(rows, contradiction_pairs, reason)

    lines.append("\nDifferences:")
    if contradiction_pairs:
        for pair in contradiction_pairs:
            lines.append("- Contradiction between %s and %s (basis: %s)"
                         % (pair.get("index_a", "?"), pair.get("index_b", "?"),
                            (pair.get("basis") or {}).get("basis", "polarity mismatch")))
    else:
        lines.append("No significant disagreement detected among the %d retrieved source(s)."
                     % len(rows))

    uncertainty = _uncertainty_text(rows, meta)
    lines.append("\nUncertainty:\n" + uncertainty)

    limitation = _limitation_text(allowed)
    lines.append("\nResearch limitation:\n" + limitation)

    lines.append("\nStatus: " + status)
    lines.append("Confidence: " + label + " (%.2f; %s)" % (value, reason))

    if filtered:
        lines.append("\n" + _filtered_note(filtered))

    lines.append("\nNo trusted memory update occurred.")
    return "\n".join(lines)


def _confidence_reason(rows, contradiction_pairs):
    if contradiction_pairs:
        return "conflicting evidence lowers confidence"
    if len(rows) >= 3:
        return "%d independent sources agree" % len(rows)
    if len(rows) == 2:
        return "2 independent sources agree"
    return "single source, no independent corroboration"


def analyze_rows(rows, conflict_map=None):
    """Answer-level status, confidence label, and belief for a source set.

    Derives the verdict through the same helpers the rendered summary uses,
    so the registry's answer context always matches the answer text. Pass
    ``conflict_map`` (row index -> contradicting indexes) to avoid the
    redundant contradiction re-detection; it is also published as
    ``extract_summary_evidence``'s analysis output.
    """
    if conflict_map is None:
        conflict_map = _conflict_index_map(rows)
    pairs = [{"index_a": a, "index_b": b}
             for a, mates in sorted(conflict_map.items()) for b in mates if a < b]
    reason = _confidence_reason(rows, pairs)
    label, value = combine_confidences(rows)
    return {
        "status": _evidence_status(rows, pairs, reason),
        "confidence": label,
        "belief": round(float(value), 2),
    }


def _persist_research_disagreements(topic, pairs, rows):
    """Persist research contradiction verdicts as neutral world-ledger notes.

    Returns the number of notes recorded. Runs only while the Maya service is
    live (so offline tests and local scripted runs never write), and only in
    the live-fetch path — cache replays are pure renders.
    """
    if not pairs:
        return 0
    try:
        pid = maya_service.running_pid()
    except Exception:
        pid = None
    if not pid:
        return 0
    by_index = {index: row for index, row in enumerate(rows)}
    recorded = 0
    try:
        import maya_world_model
        for pair in pairs:
            a = int(re.sub(r"\D", "", str(pair.get("index_a", ""))) or -1)
            b = int(re.sub(r"\D", "", str(pair.get("index_b", ""))) or -1)
            row_a = by_index.get(a)
            row_b = by_index.get(b)
            if not row_a or not row_b:
                continue
            result = maya_world_model.add_research_conflict(
                topic=topic,
                sentence_a=_first_sentence(row_a.get("snippet", "")),
                url_a=row_a.get("url", ""),
                host_a=row_a.get("host", ""),
                sentence_b=_first_sentence(row_b.get("snippet", "")),
                url_b=row_b.get("url", ""),
                host_b=row_b.get("host", ""),
            )
            if result.get("status") == "recorded":
                recorded += 1
    except Exception:
        return recorded
    return recorded


def _conflict_index_map(rows):
    """Map row index -> indexes of rows it was flagged as contradicting.

    Index-space companion to _detect_contradictions (which returns index_a
    / index_b pairs); the drilldown renders per-row conflict linkage.
    """
    flagged = {}
    for pair in _detect_contradictions(rows):
        try:
            a = int(re.sub(r"\D", "", str(pair.get("index_a", ""))) or -1)
            b = int(re.sub(r"\D", "", str(pair.get("index_b", ""))) or -1)
        except ValueError:
            continue
        if a < 0 or b < 0:
            continue
        flagged.setdefault(a, set()).add(b)
        flagged.setdefault(b, set()).add(a)
    return {index: sorted(mates) for index, mates in flagged.items()}


def _world_baseline(topic, limit=3):
    """Read-only world-baseline rows: neutral stored evidence whose claims
    share terms with the topic. Returns rows only (no writes)."""
    try:
        import maya_world_model
        rows = maya_world_model.read_evidence()
    except Exception:
        return []
    if not rows:
        return []
    topic_terms_set = set(topic_terms(topic))
    if not topic_terms_set:
        return []
    matched = []
    for row in rows[-200:]:
        claim_tokens = set(topic_terms(str(row.get("claim", ""))))
        overlap = topic_terms_set & claim_tokens
        if overlap:
            matched.append((len(overlap), row))
    matched.sort(key=lambda item: -item[0])
    return [row for _, row in matched[:limit]]


def _uncertainty_text(rows, meta):
    used_classes = sorted({row.get("class", "general") for row in rows})
    gaps = [value for value in (meta.get("classes") or [])
            if value not in used_classes]
    entropy = _entropy_report(rows)
    parts = []
    if entropy and entropy.get("items", 0) > 1:
        parts.append("Information spread across %d normalized belief item(s); normalized "
                     "entropy %.2f." % (entropy["items"], entropy["normalized_entropy"]))
    elif len(rows) == 1:
        parts.append("Single-source evidence; independent corroboration unavailable.")
    if gaps:
        parts.append("No evidence obtained from selected class(es): " + ", ".join(gaps) + ".")
    parts.append("Evidence reflects the pages retrieved at the retrieval time; "
                 "source availability affects confidence.")
    return " ".join(parts)


def _limitation_text(allowed):
    if allowed:
        hosts = ", ".join(sorted(allowed))
        host_line = "sources permitted by the local read-only network policy: " + hosts + "."
    else:
        host_line = "no network policy file was found, so public HTTPS sources were used read-only."
    return ("Automated synthesis is not expert review. This answer uses only " + host_line
            + " Restricted or paid databases are not accessible, and discovery-only "
            "general-web pages are not used as evidence.")


def research_topic(topic):
    topic = topic.strip()
    if not topic:
        return 'Please provide a topic.\nNo trusted memory update occurred.'

    status, allowed = _policy_state()
    if status != "ok":
        return ("Research is paused because the local network policy is not in read-only mode."
                "\nNo trusted memory update occurred.")

    cached = _cache_hit(topic)
    if cached is not None:
        meta = dict(cached.get("meta") or {})
        meta.setdefault("allowed_hosts", allowed)
        return _render_cached(cached, topic)

    query_meta = classify_query(topic)

    candidates, source_notes = _discover_candidates(topic, allowed, query_meta)
    candidates = dedupe_candidates(candidates)

    accepted = plan_candidates(topic, candidates, query_meta, allowed=allowed)

    evidence = []
    for candidate in accepted:
        url = candidate.get("url", "")
        try:
            raw_body = _public_fetch(url, timeout=12)
        except Exception as exc:
            evidence.append({"url": url, "title": candidate.get("title", url),
                             "host": candidate.get("host", ""),
                             "class": candidate.get("class", "general"),
                             "relevance": 0.0, "tier": "low", "belief": 0.35,
                             "snippet": "", "read_error": str(exc)[:120]})
            continue
        body_summary = _answer_summary(raw_body)
        if not _accept_evidence(topic, candidate.get("title", ""), body_summary):
            continue
        snippet = body_summary
        relevance = score_relevance(topic, candidate.get("title", ""), snippet)
        tier, belief = tier_for(candidate.get("class", "general"), relevance)
        evidence.append({"url": url, "title": candidate.get("title", url),
                         "host": candidate.get("host", ""),
                         "class": candidate.get("class", "general"),
                         "relevance": relevance, "tier": tier, "belief": belief,
                         "snippet": snippet})

    usable = [row for row in evidence if row.get("snippet")]
    if not usable:
        return f'No focused public result matched: {topic}\nNo trusted memory update occurred.'

    # Evidence-quality gate: drop contentless retrieval artifacts before
    # cache persistence and rendering. Rejected rows are exposed to
    # research_summary via meta["filtered"] for a deterministic note so
    # the user can see what was excluded and why.
    accepted_rows, rejected_rows = [], []
    for row in usable:
        decision, reason = evidence_gate_decision(row.get("snippet", ""))
        if decision == "REJECT":
            rejected_rows.append((row.get("url", ""), reason))
        else:
            accepted_rows.append(row)
    if not accepted_rows:
        return (f'No focused public result matched: {topic}\n'
                'No trusted memory update occurred.')

    meta = {
        "kind": query_meta["kind"],
        "kind_confidence": query_meta["confidence"],
        "classes": query_meta["classes"],
        "source_notes": source_notes,
        "allowed_hosts": allowed,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    if rejected_rows:
        meta["filtered"] = rejected_rows
    result = research_summary(topic, accepted_rows, meta)
    recorded = _persist_research_disagreements(topic, _detect_contradictions(accepted_rows), accepted_rows)
    if recorded:
        result += "\nRecorded %d disagreement note(s) in the neutral world ledger (review-only)." % recorded
    if not any(row.get("read_error") for row in accepted_rows):
        outcome = _write_cache(topic, meta["retrieved_at"], source_notes, accepted_rows, meta)
        if outcome in (PERSIST_WRITTEN, PERSIST_SKIPPED, PERSIST_FAILED):
            _persist_log("research cache '%s': %s (%d accepted row(s))" % (
                topic, outcome, len(accepted_rows)))
    return result