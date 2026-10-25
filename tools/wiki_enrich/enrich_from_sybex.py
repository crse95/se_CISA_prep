#!/usr/bin/env python3
"""Enrich the CISA wiki JSON with mapped content from the Sybex CISA Study Guide.

Book: Peter H. Gregory & Mike Chapple, "CISA Certified Information Systems Auditor
Study Guide", Sybex/Wiley, (c) 2025, ISBN 9781394288380 (2024-2029 objectives).
Third-party source with no URL: every added item carries basis "book" and a
book_ref (chapter, section, file, line). No URL is invented.

The book is not read by hand. Code parses headings, chapter boundaries, exam tips,
Exam Essentials, review questions (+ Appendix B answers), the assessment test,
bold definition lists and the index, then maps them to wiki domains/subtopics/
glossary terms by keyword overlap. A small set of fact checks compares book claims
with wiki values. Disagreements are written to source_conflicts_log.json (next to the
wiki) with a resolution; the wiki only gets the result as a key_facts entry.

Rerunnable: items added by a previous run (added_by == SCRIPT) are removed first.
Existing ISACA-sourced or resolved values are never changed.

Usage:
  python3 enrich_from_sybex.py [--domains D1,D2] [--out PATH] [--write]
Without --write the result goes to --out (default: a *.preview.json next to the wiki)
and the wiki is untouched. With --write the wiki is backed up, then overwritten.
"""
import argparse
import collections
import datetime
import json
import math
import pathlib
import re
import shutil
import sys

SCRIPT = "enrich_from_sybex.py"
TODAY = datetime.date.today().isoformat()
PF = pathlib.Path("/mnt/project-files")
WIKI = PF / "cisa-wiki" / "CISA exam domains wiki.json"
CONFLICT_LOG = PF / "cisa-wiki" / "source_conflicts_log.json"
# book conflict topic -> key fact shown in the wiki (None: an existing key fact already covers it)
KEY_FACT = {
    "ITAF edition in the Sybex study guide": None,
    "COBIT 2019 principle count in the Sybex study guide": (
        "COBIT 2019 principle count", "COBIT 2019: 6 governance system principles + 3 governance framework principles (COBIT 5 had 5 principles).", ["D2"]),
    "Job practice topic list in the Sybex study guide objective map": (
        "Topic list to study by", "Study by the wiki's ISACA 2024 subtopic list; use the Sybex chapters as reading material.", []),
}
PART1 = PF / "study-guide" / "sybex_cisa_study_guide_part1.md"
PART2 = PF / "study-guide" / "sybex_cisa_study_guide_part2.md"
BOOK = {
    "title": "CISA Certified Information Systems Auditor Study Guide",
    "authors": "Peter H. Gregory, Mike Chapple",
    "publisher": "Sybex/Wiley",
    "year": 2025,
    "isbn": "9781394288380",
    "objectives": "2024-2029 exam objectives (cover)",
}
BOOK_SHORT = "Sybex CISA Study Guide (Gregory & Chapple, 2025)"
CANDIDATE_GUIDE = "https://www.isaca.org/credentialing/-/media/fa494652c5f149289af38cef18328650.ashx"
OUTLINE_PAGE = "https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline"

# Chapter -> wiki domain (+ part). From the book's objective map; Ch9 is not in the
# map, it covers performing an audit, so it is mapped to D1 here (our mapping).
CHAPTER_DOMAIN = {1: ("D2", None), 2: ("D1", None), 3: ("D3", None), 4: ("D4", "A"), 5: ("D4", "A"),
                  6: ("D4", "B"), 7: ("D5", None), 8: ("D5", None), 9: ("D1", None)}
CHAPTER_TITLE = {1: "IT Governance and Management", 2: "The Audit Process", 3: "IT Life Cycle Management",
                 4: "IT Service Management", 5: "IT Infrastructure", 6: "Business Continuity and Disaster Recovery",
                 7: "Information Security Management", 8: "Identity and Access Management",
                 9: "Conducting a Professional Audit"}

NOISE_HEADINGS = {"exam tip", "note", "summary", "exam essentials", "review questions", "real world scenario",
                  "tip", "warning", "caution"}
STOP = set("""a an the and or of for to in on with by from as at is are be into its it this that these those their
their than then any all other others not no via vs versus using use used how what why which who when where per
about over under between within without through including include includes iii ii i iv v vs based type types""".split())
SYNONYMS = {  # expand wiki subtopic vocab with common book wording
    "bia": "business impact analysis", "bcp": "business continuity plan", "drp": "disaster recovery plan",
    "resilience": "resiliency resilient redundancy fault tolerance high availability cluster",
    "backup": "backups restore restoration replication", "iam": "identity access",
    "dlp": "data loss prevention", "pki": "public key infrastructure certificate", "encryption": "cryptography cipher",
    "forensics": "forensic chain custody", "sampling": "sample samples", "analytics": "caat caats analytics",
    "incident": "incidents", "problem": "problems", "patch": "patches patching", "change": "changes",
    "vendor": "outsourcing supplier suppliers third-party contract contracts sourcing",
    "privacy": "pii personal", "architecture": "zachman", "risk": "risks threat threats vulnerability",
    "testing": "test tests", "migration": "conversion cutover changeover", "shadow": "end-user euc",
    "physical": "fire suppression facility facilities sprinkler power hvac", "environmental": "humidity temperature",
    "network": "firewall firewalls router switch tcp", "endpoint": "malware antivirus edr",
    "cloud": "iaas paas saas", "virtualized": "virtualization hypervisor container",
    "mobile": "byod wireless wi-fi", "attack": "attacks phishing malware ransomware", "awareness": "training",
    "monitoring": "siem log logs", "log": "logs logging", "capacity": "performance", "database": "dbms sql",
    "scheduling": "batch", "interfaces": "api apis", "asset": "assets inventory cmdb", "components": "hardware server",
    "governance": "board steering", "strategy": "strategic", "laws": "regulation regulations legal compliance",
    "quality": "iso 9000 9001", "performance": "kpi kpis metrics balanced scorecard", "resource": "personnel hiring budget",
    "project": "projects pmbok", "feasibility": "business case", "methodologies": "sdlc agile waterfall",
    "readiness": "testing uat", "release": "releases configuration", "post-implementation": "pir",
    "evidence": "interview observation", "reporting": "report findings", "ethics": "itaf code",
    "controls": "control preventive detective corrective", "audits": "audit assessment",
}


def stem(w):
    w = w.lower().strip("-'")
    for suf, rep in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)] + rep
    return w


def toks(s):
    return [stem(w) for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", s or "") if w.lower() not in STOP and len(w) > 1]


def clean_heading(s):
    s = re.sub(r"^#+\s*", "", s).strip()
    s = s.replace("**", "").replace("*", "").strip(" :")
    return re.sub(r"\s+", " ", s)


# ---------------------------------------------------------------- book parsing
def load_book():
    p1 = PART1.read_text(encoding="utf-8").split("\n")
    p2 = PART2.read_text(encoding="utf-8").split("\n")
    if p1 and p1[-1] == "":
        p1 = p1[:-1]
    # line i (0-based) -> (file, 1-based line)
    where = [("study-guide/" + PART1.name, i + 1) for i in range(len(p1))] + \
            [("study-guide/" + PART2.name, i + 1) for i in range(len(p2))]
    return p1 + p2, where


def find_boundaries(lines):
    """Return dict of region name -> start index (0-based)."""
    b = {}
    for i, l in enumerate(lines):
        h = clean_heading(l) if l.startswith("#") else ""
        if not h:
            continue
        if i > 1200 and "objective_map" not in b and False:
            pass
        if h == "CISA Certification Exam Objective Map":
            b["objective_map"] = i
        elif h == "Assessment Test" and "assessment" not in b:
            b["assessment"] = i
        elif h == "Answers to Assessment Test":
            b["assessment_answers"] = i
        elif re.fullmatch(r"Chapter [1-8]( .*)?", h) and i > 1200 and "appendix_b" not in b:
            n = int(h.split()[1])
            b.setdefault(f"ch{n}", i)
        elif h == "Conducting a Professional Audit" and "ch9" not in b:
            b["ch9"] = i
        elif h == "Appendix A":
            b["appendix_a"] = i
        elif h == "Appendix B":
            b["appendix_b"] = i
        elif h == "Index":
            b["index"] = i
    need = ["objective_map", "assessment", "assessment_answers", "appendix_a", "appendix_b", "index"] + [f"ch{n}" for n in range(1, 10)]
    missing = [k for k in need if k not in b]
    if missing:
        sys.exit(f"book boundaries not found: {missing}")
    order = [b[f"ch{n}"] for n in range(1, 10)] + [b["appendix_a"], b["appendix_b"], b["index"]]
    if order != sorted(order):
        sys.exit(f"book boundaries out of order: {b}")
    return b


def chapter_of(i, b):
    ch = None
    for n in range(1, 10):
        if i >= b[f"ch{n}"]:
            ch = n
    return ch if ch is not None and i < b["appendix_a"] else None


class Book:
    def __init__(self):
        self.lines, self.where = load_book()
        self.b = find_boundaries(self.lines)
        self.section_at = self._sections()

    def ref(self, i, section=None):
        ch = chapter_of(i, self.b)
        f, ln = self.where[i]
        if ch:
            chap = f"Ch {ch} {CHAPTER_TITLE[ch]}"
        elif i >= self.b["appendix_b"]:
            chap = "Appendix B Answers to Review Questions"
        elif i >= self.b["appendix_a"]:
            chap = "Appendix A Popular Methodologies, Frameworks, and Guidance"
        elif i >= self.b["assessment"]:
            chap = "Assessment Test"
        else:
            chap = "Introduction"
        sec = section if section is not None else self.section_at[i]
        return {"source": BOOK_SHORT, "chapter": chap, "section": sec, "file": f, "line": ln,
                "cite": f"{BOOK_SHORT}, {chap}" + (f", section \"{sec}\"" if sec else "") + f" ({f} L{ln})"}

    def _sections(self):
        cur, out = None, []
        for l in self.lines:
            if l.startswith("#"):
                h = clean_heading(l)
                if h and h.lower() not in NOISE_HEADINGS and not re.fullmatch(r"(Chapter \d+.*|[A-Z])", h) and len(h) < 90:
                    cur = h
            out.append(cur)
        return out

    def headings(self, start, end):
        for i in range(start, end):
            l = self.lines[i]
            if l.startswith("#"):
                h = clean_heading(l)
                if h and h.lower() not in NOISE_HEADINGS and not re.match(r"Chapter \d", h) and 3 < len(h) < 90 \
                        and not h.endswith("."):
                    yield i, h

    def paragraph(self, i, max_paras=1):
        """Text from line i until a blank line (or next heading); skip leading blanks."""
        out, paras, n = [], 0, len(self.lines)
        while i < n and not self.lines[i].strip():
            i += 1
        while i < n and paras < max_paras:
            l = self.lines[i]
            if l.startswith("#"):
                break
            if not l.strip():
                paras += 1
                i += 1
                continue
            if not l.startswith("![img"):
                out.append(l.strip())
            i += 1
        return " ".join(out).strip()

    def chapter_ranges(self):
        starts = [self.b[f"ch{n}"] for n in range(1, 10)] + [self.b["appendix_a"]]
        return {n: (starts[n - 1], starts[n]) for n in range(1, 10)}


# ---------------------------------------------------------------- extraction
def extract_exam_tips(bk):
    tips = []
    for i, l in enumerate(bk.lines):
        if i < bk.b["ch1"] or i >= bk.b["appendix_b"]:
            continue
        if re.fullmatch(r"\s*#*\s*\**\s*exam tip\s*\**\s*", l, re.I):
            text = bk.paragraph(i + 1)
            if len(text) > 30:
                tips.append({"i": i, "text": text, "chapter": chapter_of(i, bk.b)})
    return tips


def chapter_block(bk, ch, title):
    s, e = bk.chapter_ranges()[ch]
    for i in range(s, e):
        if bk.lines[i].startswith("#") and clean_heading(bk.lines[i]).lower() == title:
            return i
    return None


def extract_essentials(bk):
    """Entries start at a heading or a bold line; the bold part (possibly split over lines) is the title."""
    out = []
    for ch in range(1, 9):
        s = chapter_block(bk, ch, "exam essentials")
        e = chapter_block(bk, ch, "review questions")
        if s is None or e is None:
            continue
        blocks = []
        for i in range(s + 1, e):
            l = bk.lines[i].strip()
            if not l or l.startswith("![img"):
                continue
            if l.startswith("#") or l.startswith("**"):
                blocks.append([i, re.sub(r"^#+\s*", "", l)])
            elif blocks:
                blocks[-1][1] += " " + l
        for i, raw in blocks:
            head = raw[:300]
            last = head.rfind("**")
            if last <= 0:
                continue
            title = head[:last].replace("*", "").strip()
            text = raw[last + 2:].replace("**", "").strip()
            if not text:
                continue
            out.append({"i": i, "chapter": ch, "title": re.sub(r"\s+", " ", title), "text": text})
    return out


Q_RE = re.compile(r"^\s*(\d{1,2})\.\s+(.*)")
OPT_RE = re.compile(r"^\s*([A-F])\.\s+(.*)")


def split_runons(lines, start, end):
    """Yield (index, text) with run-on items split: 'committee.12. During ...?- A. Document'."""
    for i in range(start, end):
        l = re.sub(r"^\s*-\s+(?=[A-F]\.\s)", "", lines[i])
        l = re.sub(r"^(\s*)(\d{1,2})\.\s+\2\.\s", r"\1\2. ", l)  # "1. 1. C." list-numbering artifact
        l = re.sub(r"(?<=[a-z.?)\]])(\d{1,2}\.\s+(?=[A-Z]))", r"\n\1", l)
        l = re.sub(r"(?<=[.?:])\s*-\s+([A-F]\.\s)", r"\n\1", l)
        for piece in l.split("\n"):
            yield i, piece


def parse_questions(lines, start, end):
    qs, cur = [], None
    for i, l in split_runons(lines, start, end):
        if not l.strip() or l.startswith("![img") or l.startswith("#"):
            continue
        m = Q_RE.match(l)
        if m and int(m.group(1)) == len(qs) + 1:
            cur = {"n": int(m.group(1)), "i": i, "question": m.group(2).strip(), "options": {}}
            qs.append(cur)
            continue
        if cur is None:
            continue
        m = OPT_RE.match(l)
        if m and (m.group(1) not in cur["options"]) and (m.group(1) == "A" or chr(ord(m.group(1)) - 1) in cur["options"]):
            cur["options"][m.group(1)] = m.group(2).strip()
            last = m.group(1)
            continue
        if cur["options"]:
            cur["options"][max(cur["options"])] += " " + l.strip()
        else:
            cur["question"] += " " + l.strip()
    return qs


A_RE = re.compile(r"^\s*(\d{1,2})\.\s+([A-F](?:,\s*[A-F])*(?:,? and [A-F])?)\.\s+(.*)")


def parse_answers(lines, start, end):
    ans, cur, prev_blank = {}, None, False
    for i, l in split_runons(lines, start, end):
        if l.startswith("#") or l.startswith("![img"):
            continue
        if not l.strip():
            prev_blank = True
            continue
        m = A_RE.match(l)
        if m and int(m.group(1)) == len(ans) + 1:
            cur = {"answer": re.sub(r"\s|and", "", m.group(2)).replace(",", ", "), "explanation": m.group(3).strip()}
            ans[int(m.group(1))] = cur
        elif cur:
            cur["explanation"] += ("\n" if prev_blank else " ") + l.strip()
        prev_blank = False
    return ans


def extract_review_questions(bk):
    out = []
    # Appendix B chapter blocks
    abs_ = []
    for i in range(bk.b["appendix_b"], bk.b["index"]):
        m = re.match(r"#+\s*\**Chapter (\d)", bk.lines[i])
        if m:
            abs_.append((int(m.group(1)), i))
    abs_.append((None, bk.b["index"]))
    answers = {ch: parse_answers(bk.lines, i + 1, abs_[k + 1][1]) for k, (ch, i) in enumerate(abs_[:-1])}
    for ch in range(1, 9):
        s = chapter_block(bk, ch, "review questions")
        if s is None:
            continue
        e = bk.chapter_ranges()[ch][1]
        for q in parse_questions(bk.lines, s + 1, e):
            a = answers.get(ch, {}).get(q["n"], {})
            out.append({**q, "chapter": ch, "set": f"Ch {ch} review question {q['n']}",
                        "answer": a.get("answer"), "explanation": a.get("explanation"),
                        "answer_ref_i": None})
    # assessment test: answers say "Chapter N" -> use that for the domain
    at = parse_questions(bk.lines, bk.b["assessment"] + 1, bk.b["assessment_answers"])
    aa = parse_answers(bk.lines, bk.b["assessment_answers"] + 1, bk.b["ch1"])
    for q in at:
        a = aa.get(q["n"], {})
        m = re.search(r"Chapter (\d)", a.get("explanation") or "")
        out.append({**q, "chapter": int(m.group(1)) if m else None, "set": f"Assessment test question {q['n']}",
                    "answer": a.get("answer"), "explanation": a.get("explanation")})
    return out, answers


def extract_index_terms(bk):
    terms = set()
    for i in range(bk.b["index"], len(bk.lines)):
        m = re.match(r"^\s*-?\s*([^,\d][^,]*?),\s*\d", bk.lines[i])
        if m:
            terms.add(m.group(1).strip().lower())
    return terms


DEF_ITEM = re.compile(r"^\s*-\s+\*\*([^*]{2,70}?):?\*\*:?\s+(.{30,})")


def extract_definition_items(bk):
    """Bold definition-list items inside chapters: - **Term:** text."""
    out = []
    for n, (s, e) in bk.chapter_ranges().items():
        for i in range(s, e):
            m = DEF_ITEM.match(bk.lines[i])
            if m:
                out.append({"i": i, "term": m.group(1).strip().rstrip(":"), "text": m.group(2).strip(), "chapter": n})
    return out


# ---------------------------------------------------------------- mapping
class Mapper:
    def __init__(self, wiki):
        self.subs = []  # (domain, idx, part, name, tokens)
        df = collections.Counter()
        for d in wiki["domains"]:
            for k, s in enumerate(d["subtopics"]):
                base = toks(s["name"])
                extra = []
                for w in re.findall(r"[A-Za-z\-]+", s["name"].lower()):
                    extra += toks(SYNONYMS.get(w, ""))
                ts = collections.Counter(base * 3 + extra)
                self.subs.append((d["id"], k, s.get("part"), s["name"], ts))
                df.update(set(ts))
        n = len(self.subs)
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}

    def best(self, text, domain=None, part=None, heading="", min_score=2.0):
        tt = collections.Counter(toks(text) + toks(heading) * 3)
        scored = []
        for d, k, p, name, ts in self.subs:
            if domain and d != domain:
                continue
            if part and p and p != part:
                continue
            sc = sum(min(tt[t], 3) * ts[t] * self.idf.get(t, 0) for t in tt if t in ts) / (1 + 0.15 * sum(ts.values()))
            scored.append((sc, d, k, name))
        scored.sort(reverse=True)
        if scored and scored[0][0] >= min_score:
            return scored[0]
        return None


def domain_of_chapter(ch):
    return CHAPTER_DOMAIN.get(ch, (None, None))


# ---------------------------------------------------------------- glossary
def term_variants(term):
    t = term
    abbr = re.findall(r"\(([^)]+)\)", t)
    t = re.sub(r"\([^)]*\)", "", t).strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", t)] if "/" in t else [t]
    out = set()
    if len(parts) > 1 and len(parts[-1].split()) > 1:  # "Hot / warm / cold site" -> "hot site"...
        tail = " ".join(parts[-1].split()[1:])
        out |= {p if len(p.split()) > 1 else f"{p} {tail}" for p in parts}
    else:
        out |= set(parts)
    for a in abbr:
        out |= {x.strip() for x in a.split("/") if len(x.strip()) >= 2}
    return {o.lower() for o in out if o}


DEF_START = re.compile(r"^(This (is|refers|type|technique|represents|computes|involves|typically|describes|means)|"
                       r"These are|Sometimes (known|called)|Also (known|called)|Here,|It is|An? (?!auditor|IS auditor)|"
                       r"The (person|party|members|process|practice|term|amount|maximum|minimum|ability|risk|use|act))")


def is_definitional(d):
    """Definition-shaped text. 'A/An/The ...' openings must name the term early (else e.g. 'A Wi-Fi network can ...')."""
    m = DEF_START.match(d["text"])
    if not m:
        return False
    if re.match(r"(An?|The) ", d["text"]) and not (set(tkey(d["term"])) & set(toks(" ".join(d["text"].split()[:5])))):
        return False
    return True


def tkey(s):
    return tuple(toks(re.sub(r"\([^)]*\)", "", s)))


def def_score(bk, d, keys):
    """How likely a bold list item is a definition of one of keys (higher is better)."""
    sc = 2 if is_definitional(d) else 0
    sec = set(toks(bk.section_at[d["i"]] or ""))
    if any(set(k) & sec for k in keys):
        sc += 1
    if re.match(r"(The|An?) (IS )?auditors?\b|Auditors\b", d["text"]):
        sc -= 2
    return sc


def find_book_definition(bk, defs, term):
    keys = {tkey(v) for v in term_variants(term)} - {()}
    cands = []
    for d in defs:
        dk = {tkey(d["term"])} | {tkey(x) for x in re.findall(r"\(([^)]+)\)", d["term"])}
        if keys & dk:
            sc = def_score(bk, d, keys)
            if sc >= 2:
                cands.append((sc, -d["i"], d["i"], d["text"]))
    # explicit sentence: "<Term> (ABBR)? is|are|refers to a ..." scores 3
    vs = sorted((v for v in term_variants(term) if len(v) > 3), key=len, reverse=True)
    pats = [re.compile(r"(?:^|[.:]\s+)(?:(?:An?|The)\s+)?" + re.escape(v) + r"(?:\s*\([A-Za-z/ ]+\))?\s+(?:is|are|refers to|means|describes)\s+(?:an?|the)\s+[^.]{15,300}\.", re.I) for v in vs]
    for n, (s, e) in bk.chapter_ranges().items():
        hit = None
        for i in range(s, e):
            l = bk.lines[i]
            if l.startswith("#") or len(l) < 40:
                continue
            for p in pats:
                m = p.search(l)
                if m:
                    hit = (3, -i, i, m.group(0).lstrip(".: ").strip())
                    break
            if hit:
                break
        if hit:
            cands.append(hit)
    if not cands:
        return None, None
    best = max(cands)
    return best[2], best[3]


# ---------------------------------------------------------------- fact checks
def fact_checks(bk, wiki):
    """Targeted checks of book claims against wiki values. Returns (results, conflicts, unverified)."""
    text = "\n".join(bk.lines[: bk.b["index"]])
    results, conflicts, unverified = [], [], []

    def line_of(pos):
        return text.count("\n", 0, pos)

    # 1. domain weights in the book's objective table
    om = bk.b["objective_map"]
    weights = {}
    for i in range(om - 20, om):
        m = re.match(r"\|\s*(\d)\.\s.*?\|\s*(\d+)%", bk.lines[i])
        if m:
            weights[f"D{m.group(1)}"] = int(m.group(2))
    wiki_w = {d["id"]: d["weight_percent"] for d in wiki["domains"]}
    results.append({"check": "Domain weights", "book": weights, "wiki": wiki_w,
                    "result": "agree" if weights == wiki_w else "conflict", "book_ref": bk.ref(om - 10)["cite"]})

    # 2. exam format facts
    ex = wiki["meta"]["exam"]
    for label, rx, wv, conv in [
        ("Number of questions", r"answer (\d+) questions", ex["questions"], int),
        ("Exam duration (minutes)", r"You'll have (\w+) hours to take the exam", ex["minutes"],
         lambda s: {"four": 240, "three": 180, "five": 300}.get(s.lower())),
        ("Score scale", r"scale ranging from (\d+) to (\d+)", ex["score_scale"], None),
        ("Passing score", r"passing score of (\d+)", ex["pass_score"], int),
    ]:
        m = re.search(rx, text)
        if not m:
            results.append({"check": label, "result": "not_found_in_book"})
            continue
        bv = f"{m.group(1)}-{m.group(2)}" if conv is None else conv(m.group(1))
        results.append({"check": label, "book": bv, "wiki": wv, "result": "agree" if bv == wv else "conflict",
                        "book_ref": bk.ref(line_of(m.start()))["cite"]})

    # 3. fees: wiki states US$575/US$760 (ISACA Candidate Guide) in its text
    wtxt = json.dumps(wiki)
    m = re.search(r"\$(\d{3}) for ISACA members and \$(\d{3}) for non-members", text)
    if m:
        ok = all(re.search(r"(US)?\$" + v, wtxt) for v in m.groups())
        results.append({"check": "Exam fee member/non-member", "book": f"${m.group(1)}/${m.group(2)}",
                        "wiki": "US$575/US$760 found in wiki text" if ok else "not found in wiki",
                        "result": "agree" if ok else "not_in_wiki", "book_ref": bk.ref(line_of(m.start()))["cite"]})

    # 4. ITAF edition: wiki key fact says 5th ed. (2026-02-26) is current
    itaf = next((c for c in wiki["key_facts"] if c["topic"].startswith("ITAF")), None)
    hits = [mm for mm in re.finditer(r"(fourth|4th)(?: and current)? edition", text, re.I)
            if "ITAF" in text[max(0, mm.start() - 300): mm.end() + 100]]
    if hits and itaf:
        refs = [bk.ref(line_of(h.start())) for h in hits]
        results.append({"check": "ITAF edition", "book": "4th edition, described as current", "wiki": "5th edition (2026-02-26) current",
                        "result": "conflict", "book_ref": "; ".join(r["cite"] for r in refs)})
        conflicts.append({
            "topic": "ITAF edition in the Sybex study guide",
            "isaca_position": itaf["fact"],
            "isaca_source": "; ".join(itaf["source_urls"]),
            "third_party_position": "The Sybex CISA Study Guide (2025) calls the ITAF 4th edition (2020) the current edition.",
            "third_party_source": None,
            "third_party_book_ref": [r["cite"] for r in refs],
            "third_party_source_type": "book",
            "notes": "The book was published in 2025, before ITAF 5th ed. Same issue as the resolved conflict \"ITAF edition: 4th vs 5th\".",
            "resolution": {
                "status": "resolved",
                "answer_to_study": itaf["fact"],
                "deciding_source": itaf["source_urls"],
                "deciding_source_type": "isaca",
                "reason": "ISACA decides exam facts; the ISACA press release of 26 Feb 2026 postdates the book. Taken over from the existing resolution.",
                "checked": TODAY,
            },
            "added_by": SCRIPT,
        })

    # 5. COBIT 2019 principles: book states two different counts in one paragraph (not in wiki)
    m = re.search(r"COBIT 2019 controls framework of (\w+) principles and (\d+) control objectives.{0,40}?The (\w+) principles", text)
    if m and m.group(1) != m.group(3):
        r = bk.ref(line_of(m.start()))
        results.append({"check": "COBIT 2019 principle count", "book": f"'{m.group(1)}' and '{m.group(3)}' principles in the same paragraph; {m.group(2)} objectives",
                        "wiki": "wiki gives 40 objectives (EDM5/APO14/BAI11/DSS6/MEA4), no principle count",
                        "result": "conflict (book says five, lists six; ISACA: 6 + 3 framework principles)", "book_ref": r["cite"]})
        cobit_src = "https://www.isaca.org/resources/news-and-trends/industry-news/2020/cobit-2019-and-cobit-5-comparison"
        conflicts.append({
            "topic": "COBIT 2019 principle count in the Sybex study guide",
            "isaca_position": ("COBIT 2019 has 6 governance system principles (COBIT 5 had 5) and adds 3 governance framework "
                               "principles; 40 governance and management objectives."),
            "isaca_source": cobit_src,
            "third_party_position": (f"The Sybex CISA Study Guide (2025) says COBIT 2019 has '{m.group(1)} principles and "
                                     f"{m.group(2)} control objectives' and then lists 'The {m.group(3)} principles' in the same paragraph."),
            "third_party_source": None,
            "third_party_book_ref": [r["cite"]],
            "third_party_source_type": "book",
            "notes": ("'Five' is the COBIT 5 count; the book's own list has six. The ISACA article cites COBIT 2019 Framework: "
                      "Introduction and Methodology, figure 3.5, which was not opened."),
            "link_check": "Checked 2026-10-25: the ISACA Industry News 2020 article loads (HTTP 200) and states 6 governance system principles vs 5 in COBIT 5, and three governance framework principles (conceptual model; open and flexible; aligned to major standards).",
            "resolution": {
                "status": "resolved",
                "answer_to_study": "COBIT 2019: 6 governance system principles + 3 governance framework principles. 5 principles is COBIT 5.",
                "deciding_source": [cobit_src],
                "deciding_source_type": "isaca",
                "reason": "ISACA decides; its COBIT 2019 vs COBIT 5 comparison (Industry News 2020) gives 6 vs 5 and lists the 3 framework principles. The book's 'five' contradicts its own list of six.",
                "checked": TODAY,
            },
            "added_by": SCRIPT,
        })
        wiki["meta"]["link_check"]["url_status"][cobit_src] = {
            "status": "ok", "note": "Loaded 2026-10-25 (curl): 6 governance system principles vs 5 in COBIT 5; 3 governance framework principles added.",
            "added_by": SCRIPT}
    return results, conflicts, unverified


def objective_map_conflict(bk, wiki, mapper):
    """Compare the book's job-practice topic list with the wiki's ISACA 2024 subtopics."""
    om, end = bk.b["objective_map"], bk.b["assessment"]
    dom, part, book_topics = None, None, []
    for i in range(om, end):
        l = bk.lines[i]
        m = re.search(r"\*\*Domain (\d)", l)
        if m:
            dom = f"D{m.group(1)}"
            continue
        m = re.match(r"\|\s*([AB])\.\s+([^|]+)\|", l)
        if m and dom:
            part = m.group(1)
            continue
        m = re.match(r"\|\s*(\d{1,2})\.\s+([^|]+)\|\s*(\d)\s*\|", l)
        if m and dom and part and "Supporting Tasks" not in "".join(bk.lines[max(om, i - 3): i]):
            if any("Supporting Tasks" in x for x in bk.lines[om:i]):
                break
            book_topics.append({"domain": dom, "part": part, "n": int(m.group(1)), "name": m.group(2).strip(), "chapter": int(m.group(3)), "i": i})

    def norm(s):  # 7-char prefixes so "Resiliency" ~ "Resilience"
        return {t[:7] for t in toks(s)}

    wiki_subs = [(d["id"], s.get("part"), s["name"]) for d in wiki["domains"] for s in d["subtopics"]]
    matched_wiki, book_only, renamed = set(), [], []
    for t in book_topics:
        best = max(((len(norm(t["name"]) & norm(n)) / len(norm(t["name"]) | norm(n)), d, p, n)
                    for d, p, n in wiki_subs if d == t["domain"]), default=(0,))
        if best[0] >= 0.99:
            matched_wiki.add((best[1], best[3]))
        elif best[0] >= 0.3 and best[2] == t["part"]:
            matched_wiki.add((best[1], best[3]))
            renamed.append(f"{t['domain']}{t['part']}{t['n']} book \"{t['name']}\" ~ wiki \"{best[3]}\"")
        else:
            book_only.append(f"{t['domain']}{t['part']}{t['n']} \"{t['name']}\"")
    wiki_only = [f"{d}{p} \"{n}\"" for d, p, n in wiki_subs if (d, n) not in matched_wiki]
    t = {"book_topics": len(book_topics), "book_only": book_only, "wiki_only": wiki_only, "renamed": renamed}
    if not (book_only or wiki_only):
        return t, None
    ref = bk.ref(om)
    c = {
        "topic": "Job practice topic list in the Sybex study guide objective map",
        "isaca_position": f"ISACA 2024 outline (Candidate Guide v1.26 appendix) as listed in the wiki: {len(wiki_subs)} subtopics across D1-D5.",
        "isaca_source": f"{CANDIDATE_GUIDE}; {OUTLINE_PAGE}",
        "third_party_position": (f"The book's objective map lists {len(book_topics)} job practice topics (with the 2024 weights) whose list differs from ISACA's. "
                                 f"Book topics the code could not match to a wiki subtopic: {'; '.join(book_only) or 'none'}. "
                                 f"Wiki/ISACA subtopics with no matching book topic: {'; '.join(wiki_only) or 'none'}. "
                                 f"Matched with different wording: {len(renamed)}. Some unmatched pairs are rewordings or moves "
                                 f"(e.g. book D4A 'Data Governance' vs ISACA D2A 'Data Governance and Classification')."),
        "third_party_source": None,
        "third_party_book_ref": [ref["cite"]],
        "third_party_source_type": "book",
        "notes": "Detected by code (token overlap of topic names, threshold 0.3 within the same domain and part). Book-only items such as 'Business Processes', 'IT-Related Frameworks' and 'Maturity Models' also appear in the older ISACA course outline (see conflict 'Domain 1 topic names in older ISACA course outline'). Book chapters still cover the content; use the book_refs on each wiki subtopic to find it.",
        "resolution": {
            "status": "resolved",
            "answer_to_study": "Study by the wiki's ISACA 2024 subtopic list; use the book's chapters as reading material, not as the topic list.",
            "deciding_source": [CANDIDATE_GUIDE],
            "deciding_source_type": "isaca",
            "reason": "ISACA decides exam facts. Candidate Guide v1.26 carries the current 2024 outline; the book is third-party.",
            "checked": TODAY,
        },
        "added_by": SCRIPT,
    }
    return t, c


# ---------------------------------------------------------------- main
def strip_previous(wiki):
    for d in wiki["domains"]:
        for k in ("book_exam_tips", "book_exam_essentials", "book_review_questions"):
            d.pop(k, None)
        for s in d["subtopics"]:
            s.pop("book_refs", None)
        d["third_party_resources"] = [r for r in d["third_party_resources"] if r.get("added_by") != SCRIPT]
    for g in wiki["glossary"]:
        for k in ("book_definition", "book_ref"):
            g.pop(k, None)
    for k in ("glossary", "key_facts", "unverified_items"):
        wiki[k] = [x for x in wiki[k] if x.get("added_by") != SCRIPT]
    wiki["meta"].pop("book_enrichment", None)


def enrich(wiki, domains):
    bk = Book()
    mp = Mapper(wiki)
    D = {d["id"]: d for d in wiki["domains"]}
    counts = collections.Counter()
    keep = lambda dom: dom in domains

    def sub_name(dom, k):
        return D[dom]["subtopics"][k]["name"]

    # subtopic book_refs from chapter headings
    for ch, (s, e) in bk.chapter_ranges().items():
        dom, part = domain_of_chapter(ch)
        if not keep(dom):
            continue
        for i, h in bk.headings(s, e):
            hit = mp.best(h, dom, part, min_score=1.2)
            if hit:
                st = D[dom]["subtopics"][hit[2]]
                st.setdefault("book_refs", [])
                if len(st["book_refs"]) < 12 and h not in {r["section"] for r in st["book_refs"]}:
                    r = bk.ref(i, h)
                    st["book_refs"].append({k: r[k] for k in ("chapter", "section", "file", "line")})
                    counts["subtopic_book_refs"] += 1
    counts["subtopics_with_book_refs"] = sum(1 for d in D.values() for s in d["subtopics"] if s.get("book_refs"))

    # exam tips
    for t in extract_exam_tips(bk):
        dom, part = domain_of_chapter(t["chapter"])
        if not keep(dom):
            continue
        sec = bk.section_at[t["i"]]
        hit = mp.best(t["text"], dom, part, heading=sec or "")
        D[dom].setdefault("book_exam_tips", []).append({
            "tip": t["text"], "maps_to_subtopic": sub_name(dom, hit[2]) if hit else None,
            "basis": "book", "source_type": "book", "book_ref": bk.ref(t["i"]), "added_by": SCRIPT})
        counts["exam_tips"] += 1

    # exam essentials
    for x in extract_essentials(bk):
        dom, part = domain_of_chapter(x["chapter"])
        if not keep(dom):
            continue
        hit = mp.best(x["title"] + " " + x["text"], dom, part, heading=x["title"])
        D[dom].setdefault("book_exam_essentials", []).append({
            "title": x["title"], "text": x["text"], "maps_to_subtopic": sub_name(dom, hit[2]) if hit else None,
            "basis": "book", "source_type": "book", "book_ref": bk.ref(x["i"], "Exam Essentials"), "added_by": SCRIPT})
        counts["exam_essentials"] += 1

    # review questions (+ assessment test)
    qs, _ = extract_review_questions(bk)
    q_problems = []
    for q in qs:
        dom, part = domain_of_chapter(q["chapter"])
        if not dom:
            q_problems.append(q["set"] + ": no chapter/domain")
            continue
        if not keep(dom):
            continue
        if len(q["options"]) < 2 or not q["answer"]:
            q_problems.append(f"{q['set']}: options={len(q['options'])} answer={q['answer']}")
        body = q["question"] + " " + " ".join(q["options"].values()) + " " + (q["explanation"] or "")
        hit = mp.best(body, dom, part)
        D[dom].setdefault("book_review_questions", []).append({
            "set": q["set"], "question": q["question"], "options": q["options"], "answer": q["answer"],
            "explanation": q["explanation"], "maps_to_subtopic": sub_name(dom, hit[2]) if hit else None, "mapping": "keyword",
            "basis": "book", "source_type": "book",
            "book_ref": bk.ref(q["i"], "Review Questions" if q["set"].startswith("Ch") else "Assessment Test"),
            "answer_ref": "Appendix B, " + CHAPTER_TITLE[q["chapter"]] if q["set"].startswith("Ch") else "Answers to Assessment Test",
            "added_by": SCRIPT})
        counts["review_questions"] += 1

    # glossary: book definition next to existing terms; never overwrite definition
    defs = extract_definition_items(bk)
    for g in wiki["glossary"]:
        i, txt = find_book_definition(bk, defs, g["term"])
        if i is not None:
            g["book_definition"] = txt[:600]
            g["book_ref"] = bk.ref(i)
            counts["glossary_book_definitions"] += 1
    # new glossary terms: bold definition items whose term is also a book index entry
    index = extract_index_terms(bk)
    have = set()
    for g in wiki["glossary"]:
        have |= {tkey(v) for v in term_variants(g["term"])}
    index_keys = {tkey(t) for t in index}
    seen = set()
    for d in defs:
        dom, part = domain_of_chapter(d["chapter"])
        if not keep(dom):
            continue
        term = d["term"]
        key = tkey(term)
        ok_shape = (2 <= len(key) <= 6 or re.fullmatch(r"[A-Z0-9]{2,8}", term)) and not re.search(r"[.?!]", term) \
            and 40 <= len(d["text"]) <= 700 and is_definitional(d)
        if not ok_shape or key in have or key in seen or key not in index_keys:
            continue
        seen.add(key)
        wiki["glossary"].append({"term": term, "definition": d["text"], "source_url": None, "basis": "book",
                                 "source_type": "book", "domain": dom, "book_ref": bk.ref(d["i"]),
                                 "note": "From the Sybex study guide (third-party, no URL). Term matched to the book index by code.",
                                 "added_by": SCRIPT})
        counts["glossary_new_terms"] += 1

    # the book as a third-party resource per domain
    for dom in domains:
        chs = [c for c, (dd, _) in CHAPTER_DOMAIN.items() if dd == dom]
        D[dom]["third_party_resources"].append({
            "title": f"{BOOK['title']} ({BOOK['year']})", "publisher": f"{BOOK['publisher']}; {BOOK['authors']}",
            "url": None, "type": "Book (study guide)",
            "relevance": "Chapters for this domain: " + "; ".join(f"Ch {c} {CHAPTER_TITLE[c]}" for c in chs),
            "source_type": "book", "verified": None, "isbn": BOOK["isbn"],
            "note": "Third-party; no URL. Cover says 2024-2029 exam objectives. Ch 9 mapping to D1 is ours (the book's objective map does not map Ch 9)." if dom == "D1" else "Third-party; no URL. Cover says 2024-2029 exam objectives.",
            "added_by": SCRIPT})
        counts["third_party_resources"] += 1

    # conflicts / fact checks (whole book, independent of --domains)
    checks, confs, unv = fact_checks(bk, wiki)
    om_summary, om_conf = objective_map_conflict(bk, wiki, mp)
    if om_conf:
        confs.append(om_conf)
    for c in confs:
        kf = KEY_FACT.get(c["topic"], (c["topic"], c["resolution"]["answer_to_study"], []))
        if kf:
            r = c["resolution"]
            wiki["key_facts"].append({"topic": kf[0], "fact": kf[1], "source_urls": list(r["deciding_source"]),
                                      "source_type": r["deciding_source_type"], "checked": r["checked"], "domains": kf[2],
                                      "added_by": SCRIPT})
            counts["key_facts"] += 1
    wiki["unverified_items"] += unv
    counts["unverified_items"] = len(unv)

    wiki["meta"]["book_enrichment"] = {
        "date": TODAY, "script": f"/mnt/project-files/cisa-wiki/{SCRIPT}", "book": BOOK,
        "files": [str(PART1), str(PART2)], "domains": sorted(domains),
        "method": ("Parsed by code, not read: chapter boundaries, headings, Exam Tip boxes, Exam Essentials, review questions "
                   "with Appendix B answers, assessment test, bold definition lists and the index. Mapping to subtopics uses "
                   "token overlap (stemmed, IDF-weighted, small synonym list) within the chapter's domain. Ch1=D2, Ch2=D1, "
                   "Ch3=D3, Ch4-5=D4 Part A, Ch6=D4 Part B, Ch7-8=D5 (book objective map); Ch9=D1 (our mapping). Fact checks "
                   "are targeted regexes; glossary definitions are shown next to the wiki's, not compared automatically."),
        "rules": "basis 'book' = third-party book, no URL; book_ref gives chapter, section, file and line. Existing definitions and ISACA values are not changed.",
        "counts": dict(counts), "objective_map_check": om_summary,
        "parse_warnings": q_problems,
    }
    return counts, q_problems, confs, checks


def update_conflict_log(confs, checks):
    """Replace this script's records in the conflict log; the wiki itself holds only key_facts."""
    log = json.loads(CONFLICT_LOG.read_text(encoding="utf-8")) if CONFLICT_LOG.exists() else {"conflicts": []}
    log["conflicts"] = [c for c in log["conflicts"] if c.get("added_by") != SCRIPT] + confs
    log["book_fact_checks"] = checks
    log["updated"] = TODAY
    CONFLICT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default="D1,D2,D3,D4,D5")
    ap.add_argument("--out")
    ap.add_argument("--write", action="store_true", help="back up and overwrite the wiki JSON")
    a = ap.parse_args()
    wiki = json.loads(WIKI.read_text(encoding="utf-8"))
    strip_previous(wiki)
    domains = set(a.domains.split(","))
    counts, problems, confs, checks = enrich(wiki, domains)
    data = json.dumps(wiki, ensure_ascii=False, indent=1)
    if a.write:
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        bak = WIKI.with_name(f"{WIKI.stem}.backup-{stamp}.json")
        shutil.copy2(WIKI, bak)
        WIKI.write_text(data, encoding="utf-8")
        update_conflict_log(confs, checks)
        print(f"backup: {bak}\nwrote: {WIKI}\nupdated: {CONFLICT_LOG}")
    else:
        out = pathlib.Path(a.out) if a.out else WIKI.with_name(WIKI.stem + ".preview.json")
        out.write_text(data, encoding="utf-8")
        print(f"preview written: {out} (wiki untouched)")
    print(json.dumps(dict(counts), indent=1))
    if problems:
        print(f"parse warnings ({len(problems)}):", *problems[:20], sep="\n  ")


if __name__ == "__main__":
    main()
