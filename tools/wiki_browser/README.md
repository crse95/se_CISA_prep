# CISA wiki browser

Builds a self-contained HTML page for browsing `CISA exam domains wiki.json`.

```
python3 tools/wiki_browser/build.py [WIKI_JSON] [OUTPUT_HTML]
```

Defaults: input `/mnt/project-files/cisa-wiki/CISA exam domains wiki.json`, output
`/mnt/project-files/cisa-wiki/browser/cisa-wiki-browser.html`. Core Python only.

- `template.html` holds the page. `build.py` replaces `__WIKI_JSON__` and `__BUILD_INFO__`.
- Link badges read each record's `verified` field. A URL shows as verified once any record
  with that URL has `verified: true`. URLs in fields without a `verified` flag
  (subtopic `source_urls`, trap/glossary `source_url`, conflict sources) take that shared state.
- Source conflicts are shown as ISACA vs third-party positions and never merged.
