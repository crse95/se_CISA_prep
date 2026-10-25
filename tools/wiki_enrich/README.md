# Wiki enrichment from the Sybex CISA Study Guide

`enrich_from_sybex.py` maps the Sybex study guide markdown (Gregory & Chapple, 2025, ISBN 9781394288380)
into `CISA exam domains wiki.json` by code: chapter boundaries, headings, Exam Tip boxes, Exam Essentials,
review questions with Appendix B answers, the assessment test, bold definition lists and the index.
Items are matched to domains via the book's chapter map and to subtopics by keyword overlap.

```
python3 enrich_from_sybex.py --domains D1 --out /tmp/d1.json   # subset preview, wiki untouched
python3 enrich_from_sybex.py --write                            # backup + overwrite the wiki
```

Inputs live in `/mnt/project-files/` (not in this repo). Core Python only. Rerunnable: items with
`added_by: enrich_from_sybex.py` are removed before each run. Existing definitions and ISACA values are not
changed. Book disagreements are written with their resolution to `source_conflicts_log.json` next to the wiki
(with `--write`); the wiki only gets the result as a `key_facts` entry.
