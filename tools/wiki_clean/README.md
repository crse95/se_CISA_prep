# Wiki cleanup: key facts only, no removed links

`clean_wiki.py` turns `source_conflicts` in `CISA exam domains wiki.json` into `key_facts` (topic, fact,
deciding source URLs) and strips references to conflicts and to dead, blocked or unreadable links.

```
python3 clean_wiki.py --out /tmp/preview.json   # preview, wiki and logs untouched
python3 clean_wiki.py --write                   # backup + overwrite the wiki, write the logs
```

- Full conflict records, `meta.conflict_resolution` and the Sybex fact checks go to `source_conflicts_log.json`.
  Unresolved conflicts become `unverified_items`.
- `dead_links` arrays, `blocked_removed`, dead/blocked/unreadable `url_status` entries, records left without a URL
  and uses of unreadable URLs go to `removed_links_log.json`.
- Sourced claims left with no URL get `flag: "No source URL; claim needs a source."` and an unverified item.
- Text edits are fixed strings keyed by JSON path; a rerun on a cleaned wiki reports them as not found and changes
  nothing else. Inputs live in `/mnt/project-files/cisa-wiki/` (not in this repo). Core Python only.
