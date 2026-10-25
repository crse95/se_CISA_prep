#!/usr/bin/env python3
"""Strip source-conflict and removed/dead/unreadable-link references from the CISA wiki JSON.

- source_conflicts -> key_facts (topic, fact, source_urls). Full records go to source_conflicts_log.json.
  Unresolved conflicts become unverified_items.
- dead_links arrays, blocked_removed, dead/blocked/unreadable url_status entries, records whose URL was
  removed and uses of unreadable URLs go to removed_links_log.json. Claims left without a source get a flag
  and an unverified item.
- Fixed text edits remove in-text mentions of conflicts and removed links.

Usage: python3 clean_wiki.py [--out PREVIEW.json] [--write]
Without --write a preview is written and the wiki and logs are untouched. Core Python only.
"""
import argparse
import datetime
import json
import pathlib
import re
import shutil

DIR = pathlib.Path("/mnt/project-files/cisa-wiki")
WIKI = DIR / "CISA exam domains wiki.json"
CONFLICT_LOG = DIR / "source_conflicts_log.json"
LINK_LOG = DIR / "removed_links_log.json"
TODAY = datetime.date.today().isoformat()
SCRIPT = "clean_wiki.py"
ENRICH = "enrich_from_sybex.py"
BAD = ("dead", "blocked", "unreadable")
NO_SOURCE_FLAG = "No source URL; claim needs a source."

# key facts written from the resolutions: conflict index -> (topic, fact, domains, merged indices)
FACTS = {
    0: ("Domain weights (2024 job practice)", "D1 18%, D2 18%, D3 12%, D4 26%, D5 26%. The 2019 split (21/17/12/23/27) is superseded.", ["D1", "D2", "D3", "D4", "D5"], [15, 16, 17]),
    1: ("Exam eligibility window", "Six months from registration; an extension can be bought.", [], []),
    2: ("Domain 4 Part B topic list", None, ["D4"], []),
    3: ("ITAF current edition", None, ["D1"], [32]),
    4: ("2024 job practice effective date", "New exam from 1 August 2024; prep materials from 1 May 2024.", [], [30]),
    5: ("Work experience and certification", None, [], []),
    6: ("Exam delivery", "PSI test centres or remote proctoring.", [], []),
    8: ("Scoring", "Scaled score 200-800; 450 or higher passes.", [], []),
    9: ("COBIT 2019 objective counts per domain", None, ["D2"], []),
    10: ("NIST SP 800-37 Rev. 2 publication date", None, ["D2"], []),
    11: ("Target 2013 breach scale", "About 40 million payment card accounts (Target, 19 Dec 2013) plus names/contact details of up to 70 million individuals (Target, 10 Jan 2014). The sets overlap, so \"up to 110 million\" is a combined upper bound.", ["D2"], []),
    12: ("TSB customers affected", "A significant proportion of TSB's 5.2 million customers were affected.", ["D2"], []),
    13: ("TSB regulatory fines", None, ["D2"], []),
    14: ("Former TSB CIO fine", None, ["D2"], []),
    18: ("Current CISA job practice", None, [], []),
    19: ("Application processing fee", None, [], []),
    20: ("Exam scheduling", None, [], []),
    21: ("Who sets risk appetite", None, ["D2"], []),
    22: ("Domain 1 name", None, ["D1"], []),
    23: ("Domain 1 topic names (2024)", "Use the 2024 names, e.g. 1B2 \"Audit Testing and Sampling Methodology\" and \"Audit Data Analytics\".", ["D1"], []),
    24: ("Domain 5 subtopic 5B4 name", "5B4 \"Security Monitoring Logs, Tools, and Techniques\".", ["D5"], []),
    25: ("Arthur Andersen licence surrender", None, ["D1"], []),
    27: ("MOVEit CVE identifier", "CVE-2023-34362.", ["D5"], []),
    28: ("ISO/IEC/IEEE 12207 current edition", None, ["D3"], []),
    29: ("ISO/IEC 38500 edition", None, ["D2"], []),
    31: ("Equifax: how long the inspection certificate had expired", None, ["D5"], []),
    33: ("COBIT 2019 principle count", "COBIT 2019: 6 governance system principles + 3 governance framework principles (COBIT 5 had 5 principles).", ["D2"], []),
    34: ("Topic list to study by", "Study by the wiki's ISACA 2024 subtopic list; use the Sybex chapters as reading material.", [], []),
}

UNRESOLVED = {
    7: {"item": "CISA pass rate", "reason": "ISACA publishes no pass rate. Third-party figures (about 45-60%) are vendor estimates without an ISACA source.",
        "needed_action": "Do not study a pass-rate figure.", "status": "open"},
}

# (path, old substring, new substring); paths are evaluated with resolve()
TEXT_EDITS = [
    ("domains[1].subtopics[1].exam_distinctions[2]", "COBIT 2019 core model has 40 objectives (per-domain counts conflict between sources - see source_conflicts)",
     "COBIT 2019 core model has 40 objectives: EDM 5, APO 14, BAI 11, DSS 6, MEA 4"),
    ("domains[1].real_world_examples[0].what_happened", "Scale figures vary (see source_conflicts).",
     "About 40 million payment card accounts and contact details of up to 70 million individuals were exposed (Target press releases)."),
    ("domains[1].real_world_examples[0].link_check",
     "Primary source (Senate Commerce page) returns 403 (Akamai) to curl, Chromium and WebFetch; Wayback has a 200 snapshot from 2026-02-16. The additional sources load",
     "The sources load"),
    ("domains[3].real_world_examples[2].what_happened", "(as reported by media; Maersk investor pages were unreachable, see source_conflicts)", "(as reported by media)"),
    ("domains[3].real_world_examples[2].what_happened", " (handover details vary across accounts)", ""),
    ("domains[4].real_world_examples[0].what_happened", "(19 months before it was replaced, per the House Oversight report; GAO said about 10 months)",
     "(19 months before it was replaced, per the House Oversight report)"),
    ("domains[4].real_world_examples[0].link_check",
     "certificate renewal on 29 July 2017, but states the certificate had expired 19 months earlier, not ~10 months (see source_conflicts).",
     "certificate renewal on 29 July 2017 after it had expired 19 months earlier."),
    ("domains[4].sources[9].link_check",
     "certificate renewal on 29 July 2017, but states the certificate had expired 19 months earlier, not ~10 months (see source_conflicts).",
     "certificate renewal on 29 July 2017 after it had expired 19 months earlier."),
    ("domains[1].third_party_resources[8].link_check", "Loads; says Rev. 2 was published December 2019, which conflicts with the NIST CSRC record (December 2018).",
     "Loads. Rev. 2 date per NIST CSRC: December 2018."),
    ("domains[1].sources[32].link_check", "Loads; says Rev. 2 was published December 2019, which conflicts with the NIST CSRC record (December 2018).",
     "Loads. Rev. 2 date per NIST CSRC: December 2018."),
    ("domains[3].third_party_resources[8].link_check", "Loads, but on 2026-10-24 it shows Domain 4 as 26% of the exam, not ~23%. The outdated-weight claim no longer holds.",
     "Loads; shows Domain 4 as 26% of the exam (2026-10-24)."),
    ("domains[3].sources[30].link_check", "Loads, but on 2026-10-24 it shows Domain 4 as 26% of the exam, not ~23%. The outdated-weight claim no longer holds.",
     "Loads; shows Domain 4 as 26% of the exam (2026-10-24)."),
    ("domains[3].third_party_resources[8].note", "Shows outdated ~23% weight; ISACA says 26%", None),
    ("domains[3].sources[17].note", "uses older wording / 23%", None),
    ("unverified_items[60].reason", "; Bloomberg blocked;", ";"),
    ("unverified_items[62].reason", "Maersk investor pages return 403, so USD 250-300M stays media-reported. See source_conflicts (unresolved).",
     "USD 250-300M is a Maersk estimate reported by media; the Maersk interim reports were not opened. Ghana domain-controller handover details are secondary-source."),
    ("unverified_items[63].reason", "Certificate: resolved to 19 months (House report, expiry 31 Jan 2016); see source_conflicts.",
     "Certificate expired 19 months (House report: expiry 31 Jan 2016, replaced 29 Jul 2017)."),
    ("unverified_items[82].reason", "Only source was a blocked link, removed 2026-10-24.", "No reachable source found."),
    ("unverified_items[83].reason", "Only source was a blocked link, removed 2026-10-24.", "No reachable source found."),
    ("domains[3].exam_traps[1].flag", "No source left after the blocked link was removed on 2026-10-24; claim needs a new source.", NO_SOURCE_FLAG),
    ("glossary[7].flag", "No source left after the blocked link was removed on 2026-10-24; claim needs a new source.", NO_SOURCE_FLAG),
    ("meta.link_check.rules", " Dead links were set to null or removed and are recorded in dead_links on the record that cited them.", ""),
    ("meta.method",
     ", removed dead links (recorded in dead_links), corrected the Domain 4 Part B topic list and one Domain 2 topic name against ISACA Candidate Guide v1.26, annotated every source conflict with what was found (link_check field) without resolving any silently, and moved",
     ", corrected the Domain 4 Part B topic list and one Domain 2 topic name against ISACA Candidate Guide v1.26, and moved"),
    ("meta.link_check.method", "; pages still blocked were tried with WebFetch (a separate fetcher), and the Wayback Machine availability API was queried for blocked or dead pages.",
     "; pages that still failed were tried with WebFetch (a separate fetcher)."),
    ("meta.link_check.url_status.https://en.wikipedia.org/wiki/NIST_Special_Publication_800-37.note",
     "Loads; says Rev. 2 was published December 2019, which conflicts with the NIST CSRC record (December 2018).",
     "Loads. Rev. 2 date per NIST CSRC: December 2018."),
]
# deciding sources of the key facts with no url_status entry, re-checked 2026-10-25
URL_STATUS_ADD = {
    "https://www.sec.gov/news/press/2002-89.htm": "Loaded 2026-10-25 via WebFetch: release 2002-89 of 15 June 2002; Andersen will cease practicing before the Commission by 31 Aug 2002.",
    "https://www.isaca.org/resources/isaca-journal/issues/2021/volume-6/helpsource-qa": "Loaded 2026-10-25 (curl 200).",
    "https://www.isaca.org/credentialing/cisa": "Loaded 2026-10-25 (curl 200).",
    "https://www.fca.org.uk/publication/final-notices/tsb-bank-plc-2022.pdf": "Loaded 2026-10-25 (curl 200).",
    "https://corporate.target.com/press/release/2014/01/target-provides-update-on-data-breach-and-financial-performance": "Loaded 2026-10-25 (curl 200).",
    "https://corporate.target.com/news-features/article/2013/12/target-confirms-unauthorized-access-to-payment-car": "Loaded 2026-10-25 (curl 200).",
}
# www.iso.org returns 403 to every fetcher on 2026-10-25; committee.iso.org serves the same record (withdrawn 2026-04-29, revised by 12207:2026)
URL_REPLACE = {"https://www.iso.org/standard/63712.html": "https://committee.iso.org/standard/63712.html"}

# unverified items whose subject is an unreadable or dead URL; matched by item prefix
DROP_UNVERIFIED = ["YouTube candidate (D1): 'CISA EXAM PREP - Domain 1A", "YouTube candidate (D2): 'CISA Domain 2 Governance and Management of IT Part 5 - Learn CISA (Amara",
                   "YouTube search results page"]


def resolve(root, path):
    """Return (parent, key) for a path like domains[1].sources[3].note or meta.link_check.url_status.<url>.note."""
    if path.startswith("meta.link_check.url_status."):
        rest = path[len("meta.link_check.url_status."):]
        url, key = rest.rsplit(".", 1)
        return root["meta"]["link_check"]["url_status"].get(url), key
    toks = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    cur = root
    for t in toks[:-1]:
        cur = cur[int(t[1:-1])] if t.startswith("[") else cur.get(t)
        if cur is None:
            return None, None
    last = toks[-1]
    return cur, int(last[1:-1]) if last.startswith("[") else last


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def convert_conflicts(w, clog, warn):
    sc = w.pop("source_conflicts", None)
    if sc is None:
        return
    by_topic = {c["topic"]: c for c in clog["conflicts"]}
    for c in sc:
        by_topic[c["topic"]] = c
    clog["conflicts"] = list(by_topic.values())
    if "conflict_resolution" in w["meta"]:
        clog["meta_conflict_resolution"] = w["meta"].pop("conflict_resolution")
    facts = []
    for i, (topic, fact, doms, merged) in FACTS.items():
        c = sc[i]
        r = c["resolution"]
        srcs = list(r.get("deciding_source") or [])
        for j in merged:
            srcs += [u for u in sc[j]["resolution"].get("deciding_source") or [] if u not in srcs]
        kf = {"topic": topic, "fact": fact or r["answer_to_study"], "source_urls": srcs,
              "source_type": r.get("deciding_source_type"), "checked": r.get("checked"), "domains": doms}
        if c.get("added_by") == ENRICH:
            kf["added_by"] = ENRICH
        facts.append(kf)
    used = set(FACTS) | {j for v in FACTS.values() for j in v[3]} | set(UNRESOLVED) | {26}
    missing = [i for i in range(len(sc)) if i not in used]
    if missing:
        warn.append(f"conflicts not mapped to a key fact: {missing}")
    w["key_facts"] = facts
    for i, u in UNRESOLVED.items():
        w["unverified_items"].append(dict(u, added_by=SCRIPT))
    be = w["meta"].get("book_enrichment")
    if be:
        if "fact_checks" in be:
            clog["book_fact_checks"] = be.pop("fact_checks")
        cnt = be.get("counts", {})
        if "source_conflicts" in cnt:
            cnt.pop("source_conflicts")
            cnt["key_facts"] = sum(1 for k in facts if k.get("added_by") == ENRICH)
        be["rules"] = be.get("rules", "").replace("Existing definitions, ISACA values and resolutions are not changed.",
                                                  "Existing definitions and ISACA values are not changed.")
    w["meta"]["key_facts_rule"] = "ISACA (isaca.org) decides exam facts. Other facts are decided by primary sources (company releases, regulators, government reports, standards bodies)."


def strip_links(w, llog):
    lc = w["meta"]["link_check"]
    us = lc["url_status"]
    bad = {u for u, v in us.items() if isinstance(v, dict) and v.get("status") in BAD}
    bad |= {u for u, v in llog.get("url_status", {}).items() if v.get("status") in BAD}
    for u in sorted(bad):
        if u in us:
            llog.setdefault("url_status", {})[u] = us.pop(u)
    for k in BAD:
        lc.get("url_status_legend", {}).pop(k, None)
    if "blocked_removed" in lc:
        llog["blocked_removed"] = lc.pop("blocked_removed")
    entries = llog.setdefault("entries", [])

    def log(path, kind, data):
        entries.append({"path": path, "kind": kind, "data": data, "date": TODAY})

    def walk(o, p):
        if isinstance(o, dict):
            if "dead_links" in o:
                log(p + ".dead_links", "dead_links", o.pop("dead_links"))
            for k, v in list(o.items()):
                if isinstance(v, str) and v in bad:
                    log(f"{p}.{k}", "unreadable_url", v)
                    o[k] = None
                elif isinstance(v, list) and any(isinstance(x, str) and x in bad for x in v):
                    for x in v:
                        if x in bad:
                            log(f"{p}.{k}", "unreadable_url", x)
                    o[k] = [x for x in v if x not in bad]
                else:
                    walk(v, f"{p}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{p}[{i}]")

    for k in ("domains", "cross_domain_themes", "glossary"):
        walk(w[k], k)

    # url records that no longer have a URL (book resources have none by design)
    for d in w["domains"]:
        for key in ("sources", "third_party_resources", "youtube_explainers"):
            keep = []
            for r in d.get(key, []):
                if r.get("url") is None and r.get("source_type") != "book":
                    log(f"{d['id']}.{key}", "record_without_url", r)
                else:
                    keep.append(r)
            d[key] = keep

    # unverified items about removed URLs
    keep = []
    for u in w["unverified_items"]:
        if any(u.get("item", "").startswith(p) for p in DROP_UNVERIFIED) or (u.get("url") in bad):
            log("unverified_items", "unverified_item_about_removed_url", u)
        else:
            keep.append(u)
    w["unverified_items"] = keep


def prune_url_status(w, llog):
    """Move url_status entries for URLs the wiki no longer cites (e.g. only cited by a conflict record)."""
    us = w["meta"]["link_check"]["url_status"]
    body = json.dumps({k: v for k, v in w.items() if k != "meta"}, ensure_ascii=False)
    for u in [u for u in us if u != "legend" and u not in body]:
        llog.setdefault("url_status_no_longer_cited", {})[u] = us.pop(u)


def link_summaries(w):
    """Rewrite the per-domain link-check summary items without counts of removed URLs."""
    us = w["meta"]["link_check"]["url_status"]
    urlre = re.compile(r"https?://[^\s;,\"'<>]+")

    def urls_of(o):
        return {u.rstrip(".)]") for u in urlre.findall(json.dumps(o, ensure_ascii=False))}

    for u in w["unverified_items"]:
        m = re.match(r"(D\d) \((.+?)\): \d+ distinct URLs checked on 2026-10-24", u.get("item", ""))
        if m:
            d = next(x for x in w["domains"] if x["id"] == m.group(1))
            urls = {x for x in urls_of(d) if x in us}
            part = sum(1 for x in urls if us[x].get("status") == "partial")
            u["item"] = f"{m.group(1)} ({m.group(2)}): {len(urls)} distinct URLs checked on 2026-10-24; {part} partly support their claim"
            u["reason"] = ("Some pages support only part of the claim. " if part else "All pages load and support their claim. ") + "Per-record details are in each record's link_check field."
            u["needed_action"] = "Read the link_check note on the partial records." if part else "None."
            u["status"] = "open" if part else "resolved"
        elif u.get("item", "").startswith("Cross-domain themes, glossary and source conflicts:"):
            urls = {x for k in ("cross_domain_themes", "glossary", "key_facts") for x in urls_of(w[k]) if x in us}
            part = sum(1 for x in urls if us[x].get("status") == "partial")
            u["item"] = f"Cross-domain themes, glossary and key facts: {len(urls)} distinct URLs checked; {part} partly support their claim"
            u["reason"] = "Per-record details are in each record's link_check field."
            u["needed_action"] = "Read the link_check note on the partial records." if part else "None."
            u["status"] = "open" if part else "resolved"


def flag_unsourced(w):
    """Flag sourced claims that are left with no URL and list them as unverified."""
    existing = {u.get("item") for u in w["unverified_items"]}

    def has_url(o):
        return any(o.get(k) for k in ("source_url", "url")) or any(asl(o.get(k)) for k in ("source_urls", "additional_source_urls"))

    def asl(v):
        return v if isinstance(v, list) else ([v] if v else [])

    targets = [(f"{d['id']} exam trap", t.get("confused_concepts"), d["id"], t) for d in w["domains"] for t in d.get("exam_traps", [])]
    targets += [("Theme", t.get("theme"), None, t) for t in w["cross_domain_themes"]]
    for label, name, dom, o in targets:
        if o.get("basis") == "sourced" and not has_url(o):
            o["flag"] = NO_SOURCE_FLAG
            item = f"{label}: {name}"
            if item not in existing:
                w["unverified_items"].append({"item": item, "reason": "No source URL.", "needed_action": "Find a reachable source or drop the claim.",
                                              "status": "open", **({"domain": dom} if dom else {}), "added_by": SCRIPT})


def add_target_sources(w):
    """The Target example now states the Target press-release figures, so it cites those releases."""
    kf = next((k for k in w.get("key_facts", []) if k["topic"] == "Target 2013 breach scale"), None)
    ex = next((x for d in w["domains"] for x in d["real_world_examples"] if x["name"] == "Target data breach"), None)
    if kf and ex:
        ex["additional_source_urls"] = ex.get("additional_source_urls", []) + [u for u in kf["source_urls"] if u not in ex.get("additional_source_urls", [])]


def fix_urls(w, llog):
    us = w["meta"]["link_check"]["url_status"]
    for u, note in URL_STATUS_ADD.items():
        us.setdefault(u, {"status": "ok", "note": note, "added_by": SCRIPT})
    for old, new in URL_REPLACE.items():
        txt = json.dumps(w, ensure_ascii=False)
        if old in txt:
            llog.setdefault("entries", []).append({"path": "*", "kind": "replaced_unresponsive_url", "data": {"old": old, "new": new}, "date": TODAY})
            w.clear()
            w.update(json.loads(txt.replace(old, new)))
    for k in w.get("key_facts", []):  # drop duplicates created by the replacement
        k["source_urls"] = list(dict.fromkeys(k["source_urls"]))


def apply_text(w, warn):
    for path, old, new in TEXT_EDITS:
        parent, key = resolve(w, path)
        if parent is None:
            warn.append(f"path not found: {path}")
            continue
        try:
            cur = parent[key]
        except (KeyError, IndexError):
            warn.append(f"path not found: {path}")
            continue
        if not isinstance(cur, str) or old not in cur:
            warn.append(f"text not found (already edited?): {path}")
            continue
        if new is None:
            del parent[key]
        else:
            parent[key] = cur.replace(old, new)


def leftovers(w):
    pat = re.compile(r"source_conflicts|see conflict|conflicts? (with|between)|dead_links|blocked link|\bremoved\b.*(2026-10-24|link)|Wayback|\b403\b|\b404\b", re.I)
    out = []

    def walk(o, p):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{p}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{p}[{i}]")
        elif isinstance(o, str) and pat.search(o):
            out.append(f"{p}: {o[:140]}")

    for k, v in w.items():
        walk(v, k)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    w = json.loads(WIKI.read_text(encoding="utf-8"))
    clog = load(CONFLICT_LOG, {"note": "Source conflicts and their resolutions, moved out of the wiki. The wiki keeps only the results in key_facts.",
                               "conflicts": []})
    llog = load(LINK_LOG, {"note": "Dead, blocked and unreadable links and the records that cited them, moved out of the wiki.", "entries": []})
    warn = []
    apply_text(w, warn)  # paths refer to the original indices, so text edits run first
    convert_conflicts(w, clog, warn)
    add_target_sources(w)
    strip_links(w, llog)
    fix_urls(w, llog)
    prune_url_status(w, llog)
    link_summaries(w)
    flag_unsourced(w)
    clog["updated"] = llog["updated"] = TODAY
    data = json.dumps(w, ensure_ascii=False, indent=1)
    if a.write:
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        bak = WIKI.with_name(f"{WIKI.stem}.backup-{stamp}.json")
        shutil.copy2(WIKI, bak)
        WIKI.write_text(data, encoding="utf-8")
        CONFLICT_LOG.write_text(json.dumps(clog, ensure_ascii=False, indent=1), encoding="utf-8")
        LINK_LOG.write_text(json.dumps(llog, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"backup: {bak}\nwrote: {WIKI}\nwrote: {CONFLICT_LOG}\nwrote: {LINK_LOG}")
    else:
        out = pathlib.Path(a.out) if a.out else WIKI.with_name(WIKI.stem + ".preview.json")
        out.write_text(data, encoding="utf-8")
        print(f"preview: {out} (wiki and logs untouched)")
    print(f"key_facts={len(w.get('key_facts', []))} unverified_items={len(w['unverified_items'])} "
          f"log_conflicts={len(clog['conflicts'])} log_link_entries={len(llog['entries'])}")
    for x in warn:
        print("WARN", x)
    for x in leftovers(w):
        print("LEFT", x)


if __name__ == "__main__":
    main()
