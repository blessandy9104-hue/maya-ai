# Maya Architecture — Provenance & Capability Slice

Structure record for the evidence-drilldown and capability-awareness code,
so later passes build with it rather than against it. Scope: the modules
this slice owns; the surrounding app is documented by its own batch
reports.

## Ownership map

| Concern | Owner | State owned |
|---|---|---|
| Research answers, source rows, evidence analysis | `maya_web_research.py` | research cache (transient); row verdicts (`analyze_rows`, `_conflict_index_map`); summary evidence recovery (`extract_summary_evidence`) |
| Answer registry (provenance ledger) | `maya_evidence.py` | `knowledge/evidence_registry.jsonl` — one writer (`register_answer`, idempotent, capped 50), one reader (`load_answers`) |
| World evidence store | `maya_world_model.py` | `maya_world_evidence.jsonl` — private; external reads go through the public `read_evidence()` door |
| Drilldown rendering | `maya_evidence.py` | none — pure renderers (`drilldown`, `show_sources`) over injected answers + the world door; `now=` injects the freshness clock |
| Capability self-description | `maya_capabilities.py` | `CAPABILITY_REGISTRY` (the only place a capability is declared) |
| Conversation routing / wiring | `maya_chat.py` | session id; calls owner functions, owns no provenance or capability state |

## Data flow (one direction)

```
research_topic() -> rendered answer text
    -> extract_summary_evidence()   (owner recovers rows/meta/analysis;
                                     cache first, summary parse fallback,
                                     rows normalized like the summary)
    -> register_answer()            (evidence owner records provenance;
                                     analysis delegated to research owner)
    -> answer + "Evidence IDs: ..." (tagging is additive text only)

:evidence <id> / show sources
    -> load_answers()               (registry reader)
    -> drilldown()/show_sources()   (pure renderers; world rows via
                                     read_evidence(); clock injectable)
```

## Rules later passes must keep

1. **Verdicts are computed once, by the research owner.** The registry and
   drilldown never re-derive status/confidence; they render what
   `analyze_rows` produced, so the answer text and its provenance can
   never disagree.
2. **One writer, one reader per store.** Only `register_answer` writes the
   registry; only `load_answers` reads it. Only `maya_world_model` touches
   the world file; `read_evidence()` is the only external door.
3. **Renderers stay pure.** `drilldown`/`show_sources` take data in, return
   text, write nothing. Freshness checks take `now=` for deterministic
   verification.
4. **A capability is declared exactly once** — in `CAPABILITY_REGISTRY` —
   and every self-description surface (capability report, conversational
   summary, both help lines, contextual hints) derives from it. The 57th
   suite's no-phantom check fails if an advertised command stops dispatching.
5. **Tagging is additive.** Evidence IDs are appended to answers; the
   summary body is never rewritten, and no provenance path mutates
   confidence, truth status, or the stores it reads.
6. **Degraded mode advertises only what works offline.** The
   offline fallback's capability claims derive from the registry's offline-safe
   groups (`degraded_capability_line`, `offline_improvement_mechanisms`);
   `offline_registry_audit` fails the suite if a renamed, removed, or
   unsafe group could ever be advertised by a degraded answer.

## Policy ownership (two separate gates, do not conflate)

There are two independent allowlists with different meanings; neither is a
mirror of the other:

| Gate | File | Meaning |
|---|---|---|
| Network host gate | `evolution/network_policy.json` | The only source of truth for which HTTPS hosts web access may touch. Read by `net_fetch.py`, `maya_research.py`, `maya_web_research.py`, `maya_web_search.py`, `maya_live_research.py`, and `browser_observe.py`; surfaced read-only in `maya_control_center.json` `allowed_hosts`. |
| App-control action gate | `maya_security_policy.json` `allowlist` (via `maya_security_wall.py`) | Approved owner-command actions (e.g. `{"open_spotify": {"program": ...}}`). Empty `{}` means no desktop-control actions are allowlisted, matching `maya_app_control_policy.json` `actions={}`. |

`owner_control_enabled: false` with `require_owner_token: true` is deliberate:
the wall denies everything at the first gate, and the token requirement stays
armed so that enabling owner control later always fails closed until a token is
also configured. Never silence `require_owner_token` to "fix" an audit read.
