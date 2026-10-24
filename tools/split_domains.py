#!/usr/bin/env python3
"""Split the cleaned CISA book into one file per CISA domain.

Core Python only. Splits at "# Chapter N:" headings. Front matter and Chapter 1
(exam/certification process, no domain) go to 00_front_matter.md.

Usage:
  python3 split_domains.py cisa_book_clean.md domains/
  python3 split_domains.py cisa_book_clean.md OUTDIR --range 1:1500   # subset test

Writes the domain files plus manifest.json (file, chapter, domain, line range,
question count, sha256). Exits non-zero if concatenating the files in book
order does not reproduce the input byte for byte.
"""
import argparse
import hashlib
import json
import os
import re
import sys

CHAPTER = re.compile(r'^# Chapter (\d+): (.+)$')
COVERS = re.compile(r'covers CISA Domain (\d)')

# Book chapter -> 2024 domain. The book (2020) states its chapter->domain mapping in
# each chapter intro; the 2024 outline keeps the same five domains. Names follow the
# planner (se-cisa-dashboard.html); weights are the 2024 job practice.
DOMAINS_2024 = {
    1: ('Information Systems Auditing Process', 18),
    2: ('Governance and Management of IT', 18),
    3: ('Information Systems Acquisition, Development and Implementation', 12),
    4: ('Information Systems Operations and Business Resilience', 26),
    5: ('Protection of Information Assets', 26),
}
SLUG = {1: 'audit_process', 2: 'governance_management', 3: 'acquisition_development',
        4: 'operations_resilience', 5: 'protection_assets'}


def split(lines):
    """Return list of parts: dict(name, chapter, domain, start, end) over 0-based [start, end)."""
    cuts = [(i, CHAPTER.match(t)) for i, t in enumerate(lines) if CHAPTER.match(t)]
    parts = []
    first = cuts[0][0] if cuts else len(lines)
    # front matter runs through Chapter 1 (not a domain)
    bounds = [(0, None)] + [(i, m) for i, m in cuts if m.group(1) != '1']
    for k, (start, m) in enumerate(bounds):
        end = bounds[k + 1][0] if k + 1 < len(bounds) else len(lines)
        if m is None:
            parts.append({'name': '00_front_matter.md', 'chapter': '1' if first < end else None,
                          'domain': None, 'start': start, 'end': end})
            continue
        body = ''.join(lines[start:end])
        d = COVERS.search(body)
        dom = int(d.group(1)) if d else None
        name = f'D{dom}_{SLUG[dom]}.md' if dom else f'chapter{m.group(1)}.md'
        parts.append({'name': name, 'chapter': m.group(1), 'chapter_title': m.group(2),
                      'domain': dom, 'start': start, 'end': end})
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('outdir')
    ap.add_argument('--range', help='a:b, 1-based inclusive line range (subset test)')
    args = ap.parse_args()

    with open(args.src, encoding='utf-8') as f:
        lines = f.readlines()
    if args.range:
        a, b = (int(x) for x in args.range.split(':'))
        lines = lines[a - 1:b]
    src_text = ''.join(lines)

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for p in split(lines):
        text = ''.join(lines[p['start']:p['end']])
        with open(os.path.join(args.outdir, p['name']), 'w', encoding='utf-8') as f:
            f.write(text)
        q = re.split(r'^#+ ANSWERS\s*$', text, flags=re.M)[-1]
        entry = {
            'file': p['name'],
            'book_chapter': p['chapter'],
            'book_chapter_title': p.get('chapter_title'),
            'domain_2019_per_book': p['domain'],
            'domain_2024': p['domain'],
            'domain_2024_name': DOMAINS_2024[p['domain']][0] if p['domain'] else None,
            'domain_2024_weight': DOMAINS_2024[p['domain']][1] if p['domain'] else None,
            'source_lines': [p['start'] + 1, p['end']],
            'answer_explanations': len(re.findall(r'^\s*(?:\*\*)?\d{1,3}\.(?:\*\*)? ', q, flags=re.M))
            if p['domain'] else 0,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        }
        manifest.append(entry)
        print(f"{entry['file']:<34} lines {entry['source_lines'][0]:>5}-{entry['source_lines'][1]:<5}"
              f" answers {entry['answer_explanations']}")

    rejoined = ''
    for e in manifest:
        with open(os.path.join(args.outdir, e['file']), encoding='utf-8') as f:
            rejoined += f.read()
    ok = rejoined == src_text
    with open(os.path.join(args.outdir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump({'source': os.path.basename(args.src),
                   'source_sha256': hashlib.sha256(src_text.encode('utf-8')).hexdigest(),
                   'rejoin_order': [e['file'] for e in manifest],
                   'rejoin_identical': ok, 'parts': manifest}, f, indent=2, ensure_ascii=False)
    print('rejoin identical:', ok)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
