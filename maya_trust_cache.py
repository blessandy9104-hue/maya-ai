"""Narrowly scoped, fail-closed cache for trust-registry *metadata* only.

This module exists to remove the repeated JSONL parse/read cost that
``maya_trust`` paid on every lookup, without ever caching an authorization
decision. It stores only parsed, non-authoritative registry structure:

- the parsed records exactly as they appear on disk (capability metadata,
  registry structure, immutable descriptions);
- whether any row was malformed (a validity flag tied to a registry state).

It deliberately does **not** store or return:

- authorization/refusal verdicts, owner approval, pending approval,
  revoke/grant outcomes, context/scope decisions, or action execution results;
- any derived "is trusted" fact — callers must keep evaluating the current
  record (status, owner, context, scope, approval, revocation, resource).
  ``authorize`` in ``maya_trust`` is unchanged and continues to evaluate every
  one of those on every request against the rows this cache returns.

Invalidation is deterministic and layered:

1. explicit mutation — ``invalidate()`` bumps a process generation token and is
   called by ``maya_trust.store_record`` for every ``refresh``/``grant``/
   ``revoke`` write, so a new record is visible to the very next reader;
2. file identity + metadata — dev/inode, size and mtime_ns are re-checked on
   every access, so any append/rewrite is noticed immediately;
3. content hash — the parsed rows are keyed by the sha256 of the exact bytes.
   With ``verify_content=True`` (used by the trust tests and available to any
   caller that wants it) the hash is recomputed on every access, so a content
   change that leaves size and mtime unchanged is still detected;
4. malformed/validity transition — a malformed parse is stored as such and can
   never be read as a valid record;
5. process/runtime reset — ``reset()``/``clear()`` drop everything; a fresh
   process starts empty;
6. TTL — every entry carries an expiry and is never served past it. The TTL is
   a bound on *metadata* staleness only; it is never the thing that makes an
   authorization decision fresh (that is always recomputed).

Concurrency: entries are immutable once built and are swapped atomically under
a lock, so readers never observe a partially updated entry. The cache holds at
most ``max_entries`` paths (LRU) and touches no disk of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

#: Default lifetime of a parsed-metadata entry (seconds). Bounds staleness for
#: the one fingerprint blind spot: a same-size, same-mtime content rewrite when
#: ``verify_content`` is disabled.
DEFAULT_TTL_SECONDS = 5.0

#: Default bound on the number of cached paths (LRU).
DEFAULT_MAX_ENTRIES = 32

#: Default bound on the total number of cached rows across all paths. This
#: keeps the resident footprint bounded even if a single registry is unusually
#: large; a live trust registry is a handful of records.
DEFAULT_MAX_TOTAL_ROWS = 2000

#: Sentinel distinguishing "argument omitted" from an explicit ``None``.
_UNSET = object()


def read_rows(path: Path | str) -> list[dict[str, Any]]:
    """Read and parse a JSONL file, uncached.

    This is the exact behavior ``maya_trust.load_registry`` had before caching:
    a missing file yields an empty list; an unparseable line becomes a
    ``{"malformed": True, "line": ...}`` marker row; blank lines are skipped.
    """
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                rows.append({"malformed": True, "line": line})
    return rows


def _stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class _Entry:
    """An immutable parsed-registry snapshot plus its validity fingerprint."""

    __slots__ = ("rows", "malformed", "content_hash", "file_id", "size",
                 "mtime_ns", "absent", "parsed_at", "generation")

    def __init__(self, rows, malformed, content_hash, stat, parsed_at,
                 generation):
        self.rows = rows
        self.malformed = malformed
        self.content_hash = content_hash
        self.parsed_at = parsed_at
        self.generation = generation
        if stat is None:
            self.absent = True
            self.file_id = None
            self.size = None
            self.mtime_ns = None
        else:
            self.absent = False
            self.file_id = (getattr(stat, "st_dev", 0),
                            getattr(stat, "st_ino", 0))
            self.size = stat.st_size
            self.mtime_ns = getattr(stat, "st_mtime_ns", None)

    def matches_stat(self, stat: os.stat_result | None) -> bool:
        if stat is None:
            return self.absent
        if self.absent:
            return False
        return (self.file_id == (getattr(stat, "st_dev", 0),
                                 getattr(stat, "st_ino", 0))
                and self.size == stat.st_size
                and self.mtime_ns == getattr(stat, "st_mtime_ns", None))


class TrustMetadataCache:
    """A bounded, fail-closed cache of parsed trust-registry metadata."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 max_entries: int = DEFAULT_MAX_ENTRIES,
                 max_total_rows: int = DEFAULT_MAX_TOTAL_ROWS,
                 verify_content: bool = False,
                 enabled: bool = True,
                 clock: Callable[[], float] | None = None) -> None:
        self._lock = threading.RLock()
        self._entries: "OrderedDict[str, _Entry]" = OrderedDict()
        self._ttl = float(ttl_seconds)
        self._max = max(1, int(max_entries))
        self._max_rows = max(1, int(max_total_rows))
        self._verify = bool(verify_content)
        self._enabled = bool(enabled)
        self._clock = clock if clock is not None else time.monotonic
        self._generation = 0
        self._hits = 0
        self._misses = 0
        self._invalidations = 0
        self._evictions = 0
        self._errors = 0

    # -- policy / lifecycle -------------------------------------------------

    def configure(self, *, ttl_seconds: Any = _UNSET,
                  max_entries: Any = _UNSET, max_total_rows: Any = _UNSET,
                  verify_content: Any = _UNSET,
                  enabled: Any = _UNSET, clock: Any = _UNSET) -> None:
        """Adjust cache policy. Any policy change drops existing entries so no
        entry can outlive the rule it was admitted under. ``clock=None``
        restores the default monotonic clock."""
        with self._lock:
            if ttl_seconds is not _UNSET:
                self._ttl = float(ttl_seconds)
            if max_entries is not _UNSET:
                self._max = max(1, int(max_entries))
            if max_total_rows is not _UNSET:
                self._max_rows = max(1, int(max_total_rows))
            if verify_content is not _UNSET:
                self._verify = bool(verify_content)
            if enabled is not _UNSET:
                self._enabled = bool(enabled)
            if clock is not _UNSET:
                self._clock = clock if clock is not None else time.monotonic
            self._entries.clear()
            self._generation += 1

    def invalidate(self) -> int:
        """Mark cached metadata stale after an explicit mutation.

        Entries are not mutated in place; the generation bump makes the next
        read re-parse from disk. Returns the new generation.
        """
        with self._lock:
            self._generation += 1
            self._invalidations += 1
            return self._generation

    def clear(self) -> None:
        """Drop all entries (counters are retained)."""
        with self._lock:
            self._entries.clear()
            self._generation += 1

    def reset(self) -> None:
        """Drop entries and counters (used by tests / runtime reset)."""
        with self._lock:
            self._entries.clear()
            self._generation += 1
            self._hits = self._misses = 0
            self._invalidations = self._evictions = self._errors = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "entries": len(self._entries),
                "max_entries": self._max,
                "rows": sum(len(e.rows) for e in self._entries.values()),
                "max_total_rows": self._max_rows,
                "ttl_seconds": self._ttl,
                "verify_content": self._verify,
                "generation": self._generation,
                "hits": self._hits,
                "misses": self._misses,
                "invalidations": self._invalidations,
                "evictions": self._evictions,
                "errors": self._errors,
            }

    # -- reads --------------------------------------------------------------

    def rows(self, path: Path | str) -> list[dict[str, Any]]:
        """Return parsed rows for ``path``, cached when valid.

        The returned list is a fresh list of the cached (immutable-by-contract)
        row dicts. Failure of the cache machinery falls back to an uncached
        read, which is the safe, pre-existing behavior.
        """
        p = Path(path)
        if not self._enabled:
            return read_rows(p)
        try:
            rows, _malformed = self._lookup(p)
        except Exception:  # noqa: BLE001 - fail closed to the uncached read
            with self._lock:
                self._errors += 1
            return read_rows(p)
        return list(rows)

    def malformed(self, path: Path | str) -> bool:
        """Whether the cached/actual registry currently contains malformed
        rows (metadata validity flag, never an authorization decision)."""
        p = Path(path)
        if not self._enabled:
            return any(isinstance(r, dict) and r.get("malformed") is True
                       for r in read_rows(p))
        try:
            _rows, malformed = self._lookup(p)
            return malformed
        except Exception:  # noqa: BLE001
            return any(isinstance(r, dict) and r.get("malformed") is True
                       for r in read_rows(p))

    def _lookup(self, path: Path):
        key = os.path.abspath(str(path))
        now = float(self._clock())
        with self._lock:
            entry = self._entries.get(key)
            generation = self._generation
            verify = self._verify
            ttl = self._ttl
        stat = _stat(path)

        # Fast path: metadata fingerprint unchanged, generation unchanged, and
        # within TTL. With verify_content we must still confirm the bytes.
        if (entry is not None and entry.generation == generation
                and entry.matches_stat(stat)
                and (now - entry.parsed_at) <= ttl):
            if not verify:
                self._record_hit(key, entry)
                return entry.rows, entry.malformed
            raw = self._read_bytes(path)
            digest = _hash_bytes(raw) if raw is not None else None
            if digest == entry.content_hash:
                self._record_hit(key, entry)
                return entry.rows, entry.malformed

        # Miss: read the exact bytes once, then either reuse the parsed rows
        # for identical content or parse a new immutable snapshot. The TTL is
        # an absolute lifetime: an expired entry is always re-parsed.
        raw = self._read_bytes(path)
        digest = _hash_bytes(raw) if raw is not None else None
        if (entry is not None and entry.generation == generation
                and digest == entry.content_hash
                and (now - entry.parsed_at) <= ttl):
            self._record_hit(key, entry)
            return entry.rows, entry.malformed

        rows, malformed = self._parse(raw)
        new_entry = _Entry(tuple(rows), malformed, digest, stat, now,
                           self._current_generation())
        with self._lock:
            self._misses += 1
            self._entries[key] = new_entry
            self._entries.move_to_end(key)
            self._enforce_bounds_locked()
        return new_entry.rows, new_entry.malformed

    def _enforce_bounds_locked(self) -> None:
        """Evict LRU entries until both the path bound and the row budget hold.

        The just-read entry is always retained (a single registry larger than
        the budget is still served), so the cache is bounded by
        ``max(max_total_rows, rows-in-the-largest-registry)``.
        """
        total = sum(len(e.rows) for e in self._entries.values())
        while (len(self._entries) > self._max
               or (total > self._max_rows and len(self._entries) > 1)):
            _key, old = self._entries.popitem(last=False)
            total -= len(old.rows)
            self._evictions += 1

    def _record_hit(self, key, entry):
        with self._lock:
            self._hits += 1
            if self._entries.get(key) is entry:
                self._entries.move_to_end(key)

    def _current_generation(self) -> int:
        with self._lock:
            return self._generation

    @staticmethod
    def _read_bytes(path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except OSError:
            return None

    @staticmethod
    def _parse(raw: bytes | None):
        if raw is None:
            return [], False
        rows: list[dict[str, Any]] = []
        malformed = False
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                rows.append({"malformed": True, "line": line})
                malformed = True
                continue
            if isinstance(row, dict) and row.get("malformed") is True:
                malformed = True
            rows.append(row)
        return rows, malformed
