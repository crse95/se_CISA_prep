# CISA Study Hub (planner + wiki)

`build_combined.py` puts the study planner and the wiki browser into one page. Each runs in its own
`srcdoc` frame; the shell bar switches Planner / Wiki / Side by side and shows the next study day.
Frames talk through `postMessage`.

- Planner → wiki: day panel links each domain in that day's sessions; Domains tab links each key topic
  to its wiki subtopics (`topic_map.json`) and the domain.
- Wiki → planner: each domain page shows learn/practice/review dates, hours done/planned and the next
  session, with "Show in planner/calendar". Mapped subtopics carry a "Plan: Dn · topic" pill.

The planner bundle gets one patched line (its plan `useMemo` calls `window.__cisaPlanHook`). Its
localStorage key `cisa-planner-v2` and state format are unchanged. The build fails if the patch target,
a planner topic or a mapped wiki subtopic is missing.

Rebuild after a wiki or planner change (core Python only):

    python3 build_combined.py [--planner HTML] [--wiki-json JSON] [--wiki-build BUILD_PY] [--out HTML]

Defaults point at `/mnt/project-files/` (planner, wiki JSON, `cisa-wiki/browser/build.py`, output
`combined/cisa-study-hub.html`).
