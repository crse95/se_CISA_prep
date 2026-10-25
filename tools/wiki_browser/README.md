# CISA wiki browser

Builds a self-contained HTML page for browsing `CISA exam domains wiki.json`.

```
python3 tools/wiki_browser/build.py [WIKI_JSON] [OUTPUT_HTML]
```

Defaults: input `/mnt/project-files/cisa-wiki/CISA exam domains wiki.json`, output
`/mnt/project-files/cisa-wiki/browser/cisa-wiki-browser.html`. Core Python only.

- `template.html` holds the page. `build.py` replaces `__WIKI_JSON__` and `__BUILD_INFO__`.
- Link badges read each record's `verified` field and `meta.link_check.url_status`
  (`ok`, `partial`, each with a note shown as a tooltip).
  A URL counts as verified once any record has `verified: true` or its status is `ok`/`partial`.
- Records show their `flag` and `link_check` note.
- `key_facts` (`topic`, `fact`, `source_urls`, `source_type`, `checked`, `domains`) are shown in their own view
  and on each listed domain's page. Conflict records and removed links are not part of the wiki; they live in
  `source_conflicts_log.json` and `removed_links_log.json` next to it (see `tools/wiki_clean/`).
- YouTube explainers show only thumbnail, title, channel, `description` (when the record has one) and the link.
  Thumbnails are downloaded at build time into `thumbs/` and embedded as data URIs.
- Book content (`basis: "book"`, from `tools/wiki_enrich/enrich_from_sybex.py`) is shown as its own entry
  types per domain: book exam tips, Exam Essentials and review questions (answer in a collapsed block).
  Subtopics show `book_refs`; glossary terms show `book_definition` next to the wiki definition. Book items
  have no URL and show their `book_ref` citation (chapter, section, file, line) instead.
