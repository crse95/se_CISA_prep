# CISA wiki browser

Builds a self-contained HTML page for browsing `CISA exam domains wiki.json`.

```
python3 tools/wiki_browser/build.py [WIKI_JSON] [OUTPUT_HTML]
```

Defaults: input `/mnt/project-files/cisa-wiki/CISA exam domains wiki.json`, output
`/mnt/project-files/cisa-wiki/browser/cisa-wiki-browser.html`. Core Python only.

- `template.html` holds the page. `build.py` replaces `__WIKI_JSON__` and `__BUILD_INFO__`.
- Link badges read each record's `verified` field and `meta.link_check.url_status`
  (`ok`, `partial`, `blocked`, `unreadable`, `dead`, each with a note shown as a tooltip).
  A URL counts as verified once any record has `verified: true` or its status is `ok`/`partial`.
- Records show their `link_check` note and any `dead_links` removed during a link check.
- Source conflicts are shown as ISACA vs third-party positions and never merged.
