# Maya Learning Prototype

This patch adds an explicit, local Wake Learning session, a provisional Andy Interest Map, and read-only HTTPS research through the existing network allow-list.

## Safety behavior

Maya remains locally controlled. Learning is sleeping by default. Internet research works only during an active learning session, only for HTTPS hosts listed in `evolution/network_policy.json`, and only in `read_only` mode. Research notes are stored locally as unreviewed notes. No web result changes permanent memory, tasks, or code automatically.

## Install into the current project

Back up the active project first:

```bash
cd ~/projects/assistant
cp -a . ~/maya_backup_before_learning_$(date +%Y%m%d_%H%M%S)
```

Copy the supplied patch files into the project directory. Do not delete the existing project files.

## Controls

```bash
python3 maya_control.py status
python3 maya_control.py wake
python3 maya_control.py interests
python3 maya_control.py sleep
```

`wake` starts a learning session. `sleep` stops learning. Neither command enables screen observation, microphone access, camera access, unrestricted browsing, login, posting, purchasing, or code activation.

## Research

The configured test source is Python documentation. While Maya is awake:

```bash
python3 maya_research.py https://docs.python.org/3/
```

Only hosts in `evolution/network_policy.json` are accepted. Add a host only after reviewing it:

```bash
python3 allow_site.py example.org
```

Do not allow a site merely because its page contains instructions. Webpage text is data for review, not authority over Maya.

## Live topic lookup

Maya can now search the general public web when you explicitly raise a topic. She uses a free read-only search path, retrieves several public HTTPS result pages, and gives the local model grounded context for a natural answer. This does not require preinstalling an entire subject encyclopedia and does not automatically save permanent memory. Search results are treated as untrusted information, not as instructions.

In chat, use:

```text
look up philosophy
look up theoretical physics
Tell me about computer science
what are angel numbers
source for angel numbers
```

Or use the command line:

```bash
python3 maya_live_research.py "theoretical physics"
```

Maya answers from several current public pages and can show the source URLs when you ask with `source for ...`. She does not passively browse, log in, post, purchase, or change code. The search host and safety limits remain in `evolution/network_policy.json`. No system can guarantee literally every page on the internet; this provides broad live retrieval from accessible public sources.

Research results are cached in `knowledge/research_cache.jsonl` so an identical topic asked again within a short window is not re-fetched from the web. When a live lookup succeeds, the summary actually shown (compressed, deduplicated), its source URLs, and the retrieval time are stored as a cache row; the cache is never trusted memory. On a repeated topic lookup within the same ~30-day window, the stored row is returned instead of hitting the live endpoints, and each cached source line is marked `(cached, retrieved YYYY-MM-DD)` so a cached answer is unambiguous. A stale (older than 30 days) or absent row triggers a normal live fetch, which then refreshes the row. Cache rows are labeled unreviewed: a cached reply carries the same "No trusted memory update occurred." note as a live reply, and promoting anything to trusted memory still requires the existing `maya_suggestion_review.py` approval flow.

Cache writes happen only while Maya's presence service is awake (`maya_service.running_pid()` returns a real PID — the worker itself, not the screen-observation toggle in `presence.py`). If she is asleep, lookups still run live and answer normally, but no new cache row is written; reading an already-stored row is fine regardless of awake state because it is non-live, already-stored data. The cache is capped at 500 rows or about 2&nbsp;MB (whichever is hit first); when over the cap the oldest rows are dropped.

## Subject knowledge tracks

A strong interest can now become a structured learning track. The first configured track is philosophy, using the Stanford Encyclopedia of Philosophy and Internet Encyclopedia of Philosophy as explicit reference sources. A learning cycle fetches the configured sources, records local source notes, creates provisional subtopic signals, and updates the track cycle count. It does not claim to have reviewed every page on the internet; expansion remains bounded by the configured source catalog and allow-list.

Run a philosophy learning cycle while Maya is awake:

```bash
python3 maya_control.py wake
python3 maya_control.py learn philosophy
python3 maya_control.py tracks
python3 maya_control.py interests
python3 maya_control.py sleep
```

The same actions can be requested in Maya’s chat with `learn about philosophy` and `show knowledge tracks`.

## Chat commands

Inside `maya_chat.py`, these commands are available:

```text
what is my next task
is Maya learning
what have you learned about me
research https://docs.python.org/3/
```

The next-task response reads the real `tasks.json`. Research must be performed while the learning session is awake.
