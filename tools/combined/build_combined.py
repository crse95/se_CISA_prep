#!/usr/bin/env python3
"""Build the combined CISA study page: planner and wiki in one artifact, linked both ways.

Usage: python3 build_combined.py [--planner HTML] [--wiki-json JSON] [--wiki-build BUILD_PY] [--out HTML]

Steps:
  1. Rebuild the wiki browser with the wiki's own build.py (so a wiki change only needs this rerun).
  2. Patch one line of the planner bundle so it hands each computed plan to planner_bridge.js.
     Nothing else in the planner changes; its localStorage key and state format stay the same.
  3. Check topic_map.json against the planner's key topics and the wiki's subtopic names.
  4. Put both pages into shell.html as iframe srcdoc and write the output.
"""
import argparse
import html
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PF = pathlib.Path("/mnt/project-files")
DEFAULTS = {
    "planner": PF / "planner/se-cisa-dashboard.html",
    "wiki_json": PF / "cisa-wiki/CISA exam domains wiki.json",
    "wiki_build": PF / "cisa-wiki/browser/build.py",
    "out": PF / "combined/cisa-study-hub.html",
}
# Exact bundle text; build fails if the planner bundle changes and the patch no longer applies.
PLAN_MEMO = "let D=(0,i.useMemo)(()=>_(n,a,s,e),[n,a,s,e])"
PLAN_MEMO_PATCHED = ("let D=(0,i.useMemo)(()=>{let x=_(n,a,s,e);"
                     "try{window.__cisaPlanHook&&window.__cisaPlanHook(x,e)}catch{}return x},[n,a,s,e])")


def fail(msg):
    sys.exit(f"build_combined: {msg}")


def script_tag(js):
    if "</script" in js.lower():
        fail("bridge script contains </script")
    return f"<script>\n{js}\n</script>"


def insert_before_last(doc, marker, text):
    i = doc.rfind(marker)
    if i < 0:
        fail(f"{marker} not found")
    return doc[:i] + text + doc[i:]


def planner_topics(bundle):
    found = re.findall(r'\{id:(\d),short:"[^"]*",name:"[^"]*",weight:\d+,topics:(\[[^\]]*\])', bundle)
    if len(found) != 5:
        fail(f"expected 5 planner domains with topics, found {len(found)}")
    return {d: json.loads(t) for d, t in found}


def check_topic_map(tmap, ptopics, wiki):
    subs = {(d["id"], s["name"]) for d in wiki["domains"] for s in d.get("subtopics", [])}
    errors = []
    for d, topics in ptopics.items():
        mapped = tmap.get(d, {})
        errors += [f"planner topic not mapped: D{d} {t}" for t in topics if t not in mapped]
        errors += [f"mapped topic not in planner: D{d} {t}" for t in mapped if t not in topics]
        for t, targets in mapped.items():
            errors += [f"wiki subtopic missing: {dd} {name} (for {t})" for dd, name in targets if (dd, name) not in subs]
    if errors:
        fail("topic_map.json does not match:\n  " + "\n  ".join(errors))
    return sum(len(v) for v in ptopics.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--planner", type=pathlib.Path, default=DEFAULTS["planner"])
    ap.add_argument("--wiki-json", type=pathlib.Path, default=DEFAULTS["wiki_json"])
    ap.add_argument("--wiki-build", type=pathlib.Path, default=DEFAULTS["wiki_build"])
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULTS["out"])
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        wiki_out = pathlib.Path(tmp) / "wiki.html"
        r = subprocess.run([sys.executable, str(a.wiki_build), str(a.wiki_json), str(wiki_out)],
                           capture_output=True, text=True)
        if r.returncode:
            fail(f"wiki build failed:\n{r.stdout}{r.stderr}")
        print(r.stdout.strip())
        wiki_html = wiki_out.read_text(encoding="utf-8")
    wiki = json.loads(a.wiki_json.read_text(encoding="utf-8"))

    planner = a.planner.read_text(encoding="utf-8")
    if planner.count(PLAN_MEMO) != 1:
        fail("planner bundle changed: plan useMemo line not found exactly once; update PLAN_MEMO")
    planner = planner.replace(PLAN_MEMO, PLAN_MEMO_PATCHED)

    tmap = json.loads((HERE / "topic_map.json").read_text(encoding="utf-8"))
    n_topics = check_topic_map(tmap, planner_topics(planner), wiki)
    tmap_js = json.dumps({k: v for k, v in tmap.items() if not k.startswith("_")}, ensure_ascii=False)

    # Planner bridge must run before the module bundle executes; module scripts are deferred,
    # so a classic script anywhere in the document runs first.
    pb = (HERE / "planner_bridge.js").read_text(encoding="utf-8").replace("__TOPIC_MAP__", tmap_js)
    planner = insert_before_last(planner, "</body>", script_tag(pb))
    wb = (HERE / "wiki_bridge.js").read_text(encoding="utf-8").replace("__TOPIC_MAP__", tmap_js)
    wiki_html = wiki_html + "\n" + script_tag(wb) + "\n"

    shell = (HERE / "shell.html").read_text(encoding="utf-8")
    for token in ("__PLANNER_SRCDOC__", "__WIKI_SRCDOC__"):
        if shell.count(token) != 1:
            fail(f"shell.html must contain {token} exactly once")
    out_html = (shell.replace("__PLANNER_SRCDOC__", html.escape(planner, quote=True))
                     .replace("__WIKI_SRCDOC__", html.escape(wiki_html, quote=True)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(out_html, encoding="utf-8")
    print(f"wrote {a.out} ({a.out.stat().st_size // 1024} KB); planner topics mapped: {n_topics}")


if __name__ == "__main__":
    main()
