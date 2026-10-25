#!/usr/bin/env python3
"""Split large project text files into chunks of at most ~40 KB for cheap context loading.

Chunks are derived copies. The originals stay the source of truth (enrich_from_sybex.py,
build.py and split_domains.py read them). Rerun this script after an original changes.

Markdown: hard cuts at chapter/section boundaries (SEGMENTS), then greedy packing of
heading-delimited sections; an oversized section is cut before a numbered question or a
blank line. Each chunk is an exact line slice, so concatenating chunks in manifest order
gives the original bytes.

JSON (wiki): a node that fits the budget is one chunk; a bigger dict is split by key, a
bigger list by item range. Consecutive small siblings are grouped. Recombining the chunks
in manifest order gives an equal object, and re-serialising it with indent=1,
ensure_ascii=False gives the original bytes.

Usage:
  python3 chunk_files.py [--root /mnt/project-files] [--out-root DIR] [--only NAME ...]
                         [--budget 40000] [--verify-only]
NAME is one of: sybex_part1 sybex_part2 wiki book_domains
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

BUDGET = 40_000
JSON_MARGIN = 2_000

# (label, first line 1-based) per hard segment; a segment runs to the next one's start.
SEGMENTS = {
    "sybex_part1": {
        "src": "study-guide/sybex_cisa_study_guide_part1.md",
        "out": "study-guide/chunks",
        "prefix": "p1",
        "segments": [
            ("front_matter", 1),
            ("introduction", 709),
            ("objective_map", 890),
            ("assessment_test", 1077),
            ("ch1_it_governance", 1301),
            ("ch2_audit_process", 3127),
            ("ch3_it_life_cycle", 4865),
            ("ch4_it_service_mgmt_start", 7409),
        ],
    },
    "sybex_part2": {
        "src": "study-guide/sybex_cisa_study_guide_part2.md",
        "out": "study-guide/chunks",
        "prefix": "p2",
        "segments": [
            ("ch4_it_service_mgmt_end", 1),
            ("ch5_it_infrastructure", 518),
            ("ch6_bc_dr", 2673),
            ("ch7_infosec_mgmt", 4603),
            ("ch8_iam", 6330),
            ("ch9_professional_audit", 7604),
            ("appA_frameworks", 9540),
            ("appB_review_answers", 10471),
            ("index", 10803),
        ],
    },
}
BOOK_DOMAINS = {"src_dir": "book/domains", "out": "book/domains/chunks"}
WIKI = {"src": "cisa-wiki/CISA exam domains wiki.json", "out": "cisa-wiki/chunks"}

HEADING = re.compile(r"^#{1,6} ")
QUESTION = re.compile(r"^\d{1,3}\. ")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def first_heading(lines):
    for ln in lines:
        s = ln.decode("utf-8", "replace").strip()
        if HEADING.match(s):
            return s.lstrip("#").strip().strip("*").strip()
    for ln in lines:
        s = ln.decode("utf-8", "replace").strip()
        if s:
            return s[:80]
    return ""


def cut_points(lines, a, b, rx):
    """Indices i in (a, b) where a new piece may start.

    HEADING: any heading line. QUESTION: numbered line after a blank. None: any line after a blank.
    """
    pts = []
    for i in range(a + 1, b):
        s = lines[i].decode("utf-8", "replace")
        blank_before = not lines[i - 1].strip()
        if rx is HEADING and rx.match(s):
            pts.append(i)
        elif rx is QUESTION and blank_before and rx.match(s):
            pts.append(i)
        elif rx is None and blank_before and s.strip():
            pts.append(i)
    return pts


def pack(lines, a, b, budget, levels=(HEADING, QUESTION, None)):
    """Split lines[a:b] into [(start, end)] pieces of <= budget bytes where possible."""
    size = lambda x, y: sum(len(l) for l in lines[x:y])
    if size(a, b) <= budget:
        return [(a, b)]
    if not levels:
        # No allowed cut point left: hard cut by line.
        out, s, acc = [], a, 0
        for i in range(a, b):
            if acc and acc + len(lines[i]) > budget:
                out.append((s, i))
                s, acc = i, 0
            acc += len(lines[i])
        out.append((s, b))
        return out
    bounds = [a] + cut_points(lines, a, b, levels[0]) + [b]
    units = [(bounds[k], bounds[k + 1]) for k in range(len(bounds) - 1)]
    if len(units) == 1:
        return pack(lines, a, b, budget, levels[1:])
    out, cur = [], None
    for u in units:
        if size(*u) > budget:
            if cur:
                out.append(cur)
                cur = None
            out.extend(pack(lines, u[0], u[1], budget, levels[1:]))
        elif cur and size(cur[0], u[1]) <= budget:
            cur = (cur[0], u[1])
        else:
            if cur:
                out.append(cur)
            cur = u
    if cur:
        out.append(cur)
    return out


def chunk_markdown(src, out_dir, prefix, segments, budget):
    data = src.read_bytes()
    lines = data.splitlines(keepends=True)
    starts = [s - 1 for _, s in segments] + [len(lines)]
    parts = []
    for k, (label, _) in enumerate(segments):
        pieces = pack(lines, starts[k], starts[k + 1], budget)
        for j, (x, y) in enumerate(pieces, 1):
            stem = prefix if len(segments) == 1 else f"{prefix}_{k:02d}_{label}"
            name = stem + (f"_{j:02d}" if len(pieces) > 1 else "") + ".md"
            body = b"".join(lines[x:y])
            parts.append({
                "file": name, "segment": label, "title": first_heading(lines[x:y]),
                "source_lines": [x + 1, y], "bytes": len(body), "sha256": sha(body), "_body": body,
            })
    return {"source": str(src), "source_bytes": len(data), "source_sha256": sha(data), "parts": parts}


# ---------- JSON ----------

def jdump(x):
    return json.dumps(x, ensure_ascii=False, indent=1)


def label_of(item, idx):
    if isinstance(item, dict):
        for k in ("id", "term", "theme", "topic", "name"):
            if isinstance(item.get(k), str):
                return re.sub(r"[^A-Za-z0-9]+", "-", item[k]).strip("-")[:30]
    return str(idx)


def chunk_json(node, path, names, budget, out):
    """Append chunk records (dicts with path/kind/value) for node at path, in document order."""
    if len(jdump(node).encode()) <= budget or not isinstance(node, (dict, list)) or not node:
        out.append({"path": path, "kind": "value", "value": node, "names": names})
        return
    if isinstance(node, dict):
        out.append({"path": path, "kind": "dict", "names": names})
        entries = [(k, v, names + [re.sub(r"[^A-Za-z0-9_]+", "-", k).strip("-")[:30]])
                   for k, v in node.items()]
        group_kind, wrap = "keys", lambda grp: {k: v for k, v, _ in grp}
    else:
        out.append({"path": path, "kind": "list", "names": names})
        entries = [(i, v, names + [label_of(v, i)]) for i, v in enumerate(node)]
        group_kind, wrap = "items", lambda grp: [v for _, v, _ in grp]
    grp = []

    def flush():
        if grp:
            first, last = grp[0][2][-1], grp[-1][2][-1]
            nm = names + ([first] if len(grp) == 1 else [f"{first}..{last}"])
            rec = {"path": path, "kind": group_kind, "value": wrap(grp), "names": nm}
            if group_kind == "items":
                rec["start"] = grp[0][0]
            out.append(rec)
            grp.clear()

    for k, v, nm in entries:
        if len(jdump(v).encode()) > budget and isinstance(v, (dict, list)) and v:
            flush()
            chunk_json(v, path + [k], nm, budget, out)
        else:
            if grp and len(jdump(wrap(grp + [(k, v, nm)])).encode()) > budget:
                flush()
            grp.append((k, v, nm))
    flush()


def recombine(records):
    root = None

    def at(path):
        n = root
        for p in path:
            n = n[p]
        return n

    def put(path, val):
        nonlocal root
        if not path:
            root = val
            return
        parent = at(path[:-1])
        if isinstance(parent, dict):
            parent[path[-1]] = val
        else:
            assert path[-1] == len(parent), f"list order broken at {path}"
            parent.append(val)

    for r in records:
        if r["kind"] == "value":
            put(r["path"], r["value"])
        elif r["kind"] == "dict":
            put(r["path"], {})
        elif r["kind"] == "list":
            put(r["path"], [])
        elif r["kind"] == "keys":
            at(r["path"]).update(r["value"])
        elif r["kind"] == "items":
            tgt = at(r["path"])
            assert r["start"] == len(tgt), f"list order broken at {r['path']}"
            tgt.extend(r["value"])
    return root


def chunk_wiki(src, budget):
    data = src.read_bytes()
    obj = json.loads(data)
    recs = []
    # Leave room for the {"path", "kind", "value"} wrapper and deeper indentation.
    chunk_json(obj, [], [], budget - JSON_MARGIN, recs)
    parts = []
    n = 0
    for r in recs:
        if r["kind"] in ("dict", "list"):
            parts.append({"file": None, "path": r["path"], "kind": r["kind"]})
            continue
        n += 1
        stem = "_".join(str(x) for x in r["names"]) or "root"
        name = f"{n:02d}_{re.sub(r'[^A-Za-z0-9_.-]+', '-', stem)[:80]}.json"
        body = {"path": r["path"], "kind": r["kind"], "value": r["value"]}
        if "start" in r:
            body["start"] = r["start"]
        b = (jdump(body) + "\n").encode()
        parts.append({"file": name, "path": r["path"], "kind": r["kind"], "bytes": len(b),
                      "sha256": sha(b), "_body": b})
    return {"source": str(src), "source_bytes": len(data), "source_sha256": sha(data),
            "rebuild": "json.dumps(obj, ensure_ascii=False, indent=1)", "parts": parts}


def wiki_records(out_dir, manifest):
    recs = []
    for p in manifest["parts"]:
        if p["file"] is None:
            recs.append({"path": p["path"], "kind": p["kind"]})
        else:
            recs.append(json.loads((out_dir / p["file"]).read_text(encoding="utf-8")))
    return recs


# ---------- write / verify ----------

def write(out_dir, manifest, key):
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in manifest["parts"]:
        if p.get("file"):
            (out_dir / p["file"]).write_bytes(p.pop("_body"))
    mpath = out_dir / "manifest.json"
    allm = json.loads(mpath.read_text()) if mpath.exists() else {}
    new = {p.get("file") for p in manifest["parts"]}
    for p in allm.get(key, {}).get("parts", []):  # chunks of the previous run that no longer exist
        if p.get("file") and p["file"] not in new and (out_dir / p["file"]).exists():
            (out_dir / p["file"]).unlink()
    allm[key] = manifest
    mpath.write_text(json.dumps(allm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_index(out_dir, allm)


def write_index(out_dir, allm):
    rows = ["# Chunk index", "",
            "Derived copies made by chunk_files.py. Originals are the source of truth.",
            "Rejoin: concatenate files in this order (Markdown) or recombine per manifest.json (JSON).", ""]
    for key, m in allm.items():
        rows += [f"## {key}", "", f"Source: `{m['source']}` ({m['source_bytes']:,} bytes)", ""]
        if m["parts"] and "source_lines" in m["parts"][0]:
            rows += ["| file | lines | KB | title |", "|---|---|---|---|"]
            for p in m["parts"]:
                t = p["title"].replace("|", "/")[:70]
                rows.append(f"| {p['file']} | {p['source_lines'][0]}-{p['source_lines'][1]} "
                            f"| {p['bytes'] / 1000:.1f} | {t} |")
        else:
            rows += ["| file | JSON path | kind | KB |", "|---|---|---|---|"]
            for p in m["parts"]:
                if p["file"]:
                    rows.append(f"| {p['file']} | `{'/'.join(map(str, p['path'])) or '/'}` "
                                f"| {p['kind']} | {p['bytes'] / 1000:.1f} |")
        rows.append("")
    (out_dir / "INDEX.md").write_text("\n".join(rows), encoding="utf-8")


def verify(out_dir, key):
    m = json.loads((out_dir / "manifest.json").read_text())[key]
    src = pathlib.Path(m["source"]).read_bytes()
    if sha(src) != m["source_sha256"]:
        return False, "original changed since chunking; rerun"
    big = [p["file"] for p in m["parts"] if p.get("bytes", 0) > BUDGET_RUN]
    if m["parts"] and "source_lines" in m["parts"][0]:
        joined = b"".join((out_dir / p["file"]).read_bytes() for p in m["parts"])
        ok = joined == src
    else:
        obj = recombine(wiki_records(out_dir, m))
        ok = obj == json.loads(src) and jdump(obj).encode() == src
    n = sum(1 for p in m["parts"] if p.get("file"))
    return ok, f"{n} chunks, max {max(p.get('bytes', 0) for p in m['parts']):,} B, over budget: {big or 'none'}"


def main():
    global BUDGET_RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/mnt/project-files")
    ap.add_argument("--out-root", help="write chunks under this dir instead of --root (for tests)")
    ap.add_argument("--only", nargs="*", default=["sybex_part1", "sybex_part2", "wiki", "book_domains"])
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()
    BUDGET_RUN = a.budget
    root = pathlib.Path(a.root)
    out_root = pathlib.Path(a.out_root) if a.out_root else root
    jobs = []
    for key in a.only:
        if key in SEGMENTS:
            c = SEGMENTS[key]
            jobs.append((key, out_root / c["out"],
                         lambda c=c: chunk_markdown(root / c["src"], None, c["prefix"], c["segments"], a.budget)))
        elif key == "wiki":
            jobs.append((key, out_root / WIKI["out"], lambda: chunk_wiki(root / WIKI["src"], a.budget)))
        elif key == "book_domains":
            man = json.loads((root / BOOK_DOMAINS["src_dir"] / "manifest.json").read_text())
            for f in man["rejoin_order"]:
                stem = f[:-3]
                jobs.append((f"book_{stem}", out_root / BOOK_DOMAINS["out"],
                             lambda f=f, stem=stem: chunk_markdown(
                                 root / BOOK_DOMAINS["src_dir"] / f, None, stem, [(stem, 1)], a.budget)))
        else:
            sys.exit(f"unknown --only value: {key}")
    bad = 0
    for key, out_dir, make in jobs:
        if not a.verify_only:
            write(out_dir, make(), key)
        ok, msg = verify(out_dir, key)
        bad += not ok
        print(f"{'OK ' if ok else 'FAIL'} {key}: {msg}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
