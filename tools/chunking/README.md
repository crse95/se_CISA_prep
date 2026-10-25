# chunk_files.py

Splits large project files in `/mnt/project-files` into chunks of at most ~40 KB (about 10k tokens). Core Python only.

Chunks are derived copies. The originals stay the source of truth. Rerun after an original changes; `--verify-only` reports a changed original.

| source | chunks |
|---|---|
| `study-guide/sybex_cisa_study_guide_part{1,2}.md` | `study-guide/chunks/` (by chapter, then section) |
| `cisa-wiki/CISA exam domains wiki.json` | `cisa-wiki/chunks/` (by JSON key / item range) |
| `book/domains/*.md` | `book/domains/chunks/` |

Each chunks folder has `INDEX.md` (file, line range or JSON path, size, title) and `manifest.json` (hashes, rejoin data).

Checks: Markdown chunks concatenated in manifest order equal the original bytes. JSON chunks recombined (see `recombine()`) equal the original object, and `json.dumps(obj, ensure_ascii=False, indent=1)` equals the original bytes.

```
python3 chunk_files.py                                  # all sources
python3 chunk_files.py --out-root /tmp/t --only wiki    # test run to another dir
python3 chunk_files.py --verify-only
```
