# Wiki verification (2026-10-25)

This folder checks the wiki records that had no checked source. It covers the 35 `unverified_paraphrase` glossary terms, the D4 trap "SDO vs RTO", and the four claims that lost their only source when dead links were removed. Two sources were used:

1. **Sybex CISA Study Guide**, a third-party book (`sybex_check_results.json`, report `unverified_vs_sybex.md`). The book text was searched by keyword, then each matching passage was read. A match is labelled book-supported, not ISACA-verified.
2. **Online primary sources** (`web_check_results.json`). The order was the ISACA glossary (isaca.org/resources/glossary, which loads now), then NIST, IEC, IIA, regulators and vendors. Each URL was fetched in the session. The file stores a quote and a source type per record, plus updates to `unverified_items`.

```
python3 apply_checks.py           # dry run: prints match counts
python3 apply_checks.py --write   # backs up, then writes the wiki
```

`apply_checks.py` adds `sybex_check`, `book_refs` and `verification` to the matched records. Verified records get `basis: sourced` and the source URL. Partial, not-verified and conflict records keep a `flag`. The script also updates the matching `unverified_items`, adds new URLs to `meta.link_check.url_status`, and replaces a few stale notes, such as the SSDF draft status and the OWASP Top 10:2025 release status. It is idempotent. `apply_sybex_check.py` is the earlier book-only version.

The scripts expect to run from `/mnt/project-files/cisa-wiki/sybex_check/`, because the wiki JSON is one level up. After a write, rerun `chunk_files.py` and `wiki_browser/build.py`. Core Python only.

Open conflict, not resolved: **Detection risk**. The ISACA glossary ties it to the enterprise's internal controls. The wiki, the Sybex guide and auditing standards define it as the auditor's procedures failing to detect a material error.
