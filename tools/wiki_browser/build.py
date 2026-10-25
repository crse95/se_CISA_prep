#!/usr/bin/env python3
"""Embed the CISA wiki JSON into template.html to produce a self-contained browser page.

Usage: python3 build.py [WIKI_JSON] [OUTPUT_HTML]

YouTube thumbnails (i.ytimg.com hqdefault) are cached in thumbs/ next to this script and embedded
as data URIs, so the page does not depend on loading external images. A failed download falls back
to the i.ytimg.com URL in the page.
"""
import base64
import datetime
import json
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_IN = pathlib.Path("/mnt/project-files/cisa-wiki/CISA exam domains wiki.json")
DEFAULT_OUT = pathlib.Path("/mnt/project-files/cisa-wiki/browser/cisa-wiki-browser.html")
REQUIRED = ["meta", "domains", "cross_domain_themes", "glossary", "key_facts", "unverified_items"]


def embed(obj):
    # "<" escaped so the JSON cannot close the <script> tag; still valid JSON.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def thumbs(wiki):
    cache = HERE / "thumbs"
    cache.mkdir(exist_ok=True)
    out = {}
    for d in wiki["domains"]:
        for v in d.get("youtube_explainers", []):
            m = re.search(r"[?&]v=([\w-]{11})", v.get("url") or "")
            vid = v.get("video_id") or (m and m.group(1))
            if not vid:
                continue
            f = cache / f"{vid}.jpg"
            if not f.exists():
                try:
                    with urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", timeout=20) as r:
                        f.write_bytes(r.read())
                except OSError as e:
                    print(f"thumbnail {vid}: {e}")
                    continue
            out[vid] = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
    return out


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
        "thumbs": thumbs(wiki),
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
    print(f"domains={len(wiki['domains'])} key_facts={len(wiki['key_facts'])} "
          f"unverified_items={len(wiki['unverified_items'])} url_records_verified={verified}/{len(records)}")


if __name__ == "__main__":
    main()
