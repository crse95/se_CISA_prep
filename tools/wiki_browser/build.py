#!/usr/bin/env python3
"""Embed the CISA wiki JSON into template.html to produce a self-contained browser page.

Usage: python3 build.py [WIKI_JSON] [OUTPUT_HTML]
"""
import datetime
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_IN = pathlib.Path("/mnt/project-files/cisa-wiki/CISA exam domains wiki.json")
DEFAULT_OUT = pathlib.Path("/mnt/project-files/cisa-wiki/browser/cisa-wiki-browser.html")
REQUIRED = ["meta", "domains", "cross_domain_themes", "glossary", "source_conflicts", "unverified_items"]


def embed(obj):
    # "<" escaped so the JSON cannot close the <script> tag; still valid JSON.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def main():
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    wiki = json.loads(src.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in wiki]
    if missing:
        sys.exit(f"wiki JSON is missing top-level keys: {missing}")

    build = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source_name": src.name,
    }
    html = (HERE / "template.html").read_text(encoding="utf-8")
    for token in ("__WIKI_JSON__", "__BUILD_INFO__"):
        if html.count(token) != 1:
            sys.exit(f"template.html must contain {token} exactly once")
    html = html.replace("__WIKI_JSON__", embed(wiki)).replace("__BUILD_INFO__", embed(build))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    records = [r for d in wiki["domains"] for k in ("sources", "third_party_resources", "real_world_examples", "youtube_explainers") for r in d.get(k, [])]
    verified = sum(1 for r in records if r.get("verified") is True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    print(f"domains={len(wiki['domains'])} conflicts={len(wiki['source_conflicts'])} "
          f"unverified_items={len(wiki['unverified_items'])} url_records_verified={verified}/{len(records)}")


if __name__ == "__main__":
    main()
