import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "knowledge"


def documents():
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"}:
            try:
                yield path, path.read_text(encoding="utf-8")
            except OSError:
                continue


def search(query):
    terms = [term.lower() for term in query.split() if term.strip()]
    results = []
    for path, text in documents():
        lower = text.lower()
        score = sum(lower.count(term) for term in terms)
        if score:
            results.append((score, path, text))
    return sorted(results, key=lambda item: (-item[0], str(item[1])))


def render_search(query):
    """Read-only search surface for the chat layer.

    Returns a rendered result list with scores, paths, and a brief excerpt.
    Always returns a string (honest refusal on empty input or no matches) and
    never writes, so ``maya_local_command`` can dispatch it safely.
    """
    query = " ".join((query or "").split()).strip()
    if not query:
        return ("Use :knowledge search <terms> to scan approved local "
                "knowledge. Nothing was written.")
    matches = search(query)
    if not matches:
        return ("No approved knowledge found for '%s'. Nothing was written; "
                "no trusted memory update occurred." % query)
    lines = ["Approved local knowledge matches for: %s" % query]
    for score, path, text in matches:
        excerpt = " ".join(text.split())[:200]
        lines.append("[%d match(es)] %s" % (score, path))
        lines.append("  " + excerpt)
    lines.append("Read-only search; no writes, no trusted memory update "
                 "occurred.")
    return "\n".join(lines)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print("Usage: python3 knowledge_search.py <search terms>")
        raise SystemExit(2)
    matches = search(query)
    if not matches:
        print("No approved knowledge found.")
        raise SystemExit(0)
    for score, path, text in matches:
        print(f"[{score} match(es)] {path}")
        print(text[:1200].rstrip())
        print("---")
