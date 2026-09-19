# Maya build order: hardware-feasible product path

## What can be done first

Maya’s product ideas divide into five practical layers. The first layer is already usable: a local supervised assistant with deterministic opportunity mapping, public read-only research, service controls, task visibility, approval-gated memory, and Presence Mode disabled by default. The second layer should be implemented next because it is CPU-friendly and directly improves usefulness: better cross-turn relevance, concise-response handling, and a review-only emerging-interest report. The third layer is the first validation milestone: demonstrate one opportunity map, one emerging-interest hypothesis review, and one reversible next experiment with a supporter.

The fourth layer requires more testing rather than more intelligence: persistent SQLite memory, correction and deletion workflows, mobile packaging, and Google Calendar OAuth. The fifth layer is deliberately later: broad autonomous web learning, background observation, external application control, predictive decisions, automatic memory promotion, and any system that changes Maya’s permissions or code without explicit human approval.

## Implemented in this pass

This pass adds a deterministic Emerging Interests review. It reads only the existing reviewable interest profile and provisional interest map, excludes the lifestyle category from cross-interest inference by default, produces hypotheses rather than facts, shows evidence and confidence, and writes nothing. It is exposed through `:emerging`, `emerging interests`, and `show emerging interests`.

The conversation context handler is also strengthened conservatively. Short follow-ups such as “what about that?”, “and the other one?”, “why?”, or “make it shorter” are linked to the most recent user turn, while the prompt context now emphasizes the latest request, the active topic, and requested answer length. No permissions, observation settings, or memory policy are changed.

## Later, after validation

SQLite should replace scattered JSON state only after a backup/export format and migration test exist. The intent classifier can be improved with more benchmark cases, but it should remain a routing aid rather than an authority. Calendar integration should remain explicit, user-authenticated, and read-only until the user deliberately enables a scoped action. Mobile should package the same guarded workflows rather than introduce new capabilities.

## Non-goals for the current hardware

Maya should not be marketed as a general autonomous agent, a surveillance system, a guaranteed predictor of interests, a financial adviser, or a self-modifying intelligence. CPU-only Ollama conversation remains a latency constraint; the deterministic local path is therefore the reliable demonstration surface.
