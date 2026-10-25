"""Apply sybex_check_results.json to the CISA wiki JSON.

Adds `sybex_check` (status, label, note, checked) and `book_refs` to each matched
record. Matching: glossary by `term`, themes by `theme`, exam traps by domain id +
`confused_concepts`.
Does not change `basis` or `verified`: a book match is third-party support, not
ISACA verification. Idempotent. Usage:
  python3 apply_sybex_check.py [--write]   (default: dry run, prints a summary)
"""
import json, shutil, sys, time, os
HERE = os.path.dirname(os.path.abspath(__file__))
WIKI = os.path.join(HERE, '..', 'CISA exam domains wiki.json')
RES = os.path.join(HERE, 'sybex_check_results.json')
CHECKED = '2026-10-25'


def main():
    wiki = json.load(open(WIKI, encoding='utf-8'))
    res = json.load(open(RES, encoding='utf-8'))
    gl = {g.get('term'): g for g in wiki.get('glossary', [])}
    traps = {(d['id'], t.get('confused_concepts')): t
             for d in wiki['domains'] for t in d.get('exam_traps', [])}
    themes = {t.get('theme'): t for t in wiki.get('cross_domain_themes', [])}
    hit, miss = 0, []
    for r in res:
        if r['kind'] == 'glossary':
            rec = gl.get(r['term'])
        elif r['kind'] == 'theme':
            rec = themes.get(r['theme'])
        else:
            rec = traps.get((r['domain'], r['confused_concepts']))
        if rec is None:
            miss.append(r.get('term') or r.get('theme') or r['confused_concepts'])
            continue
        hit += 1
        rec['sybex_check'] = {'status': r['status'], 'label': r['label'], 'note': r['note'], 'checked': CHECKED}
        if r['book_refs']:
            rec['book_refs'] = r['book_refs']
        else:
            rec.pop('book_refs', None)
        # A flag that says "no source" is still true for ISACA; record the book support next to it.
        if 'flag' in rec and r['status'] in ('supported', 'partial'):
            base = rec['flag'].split(' Sybex guide:')[0]
            rec['flag'] = base + ' Sybex guide: ' + r['label'] + ' (third-party); an ISACA or primary source is still needed.'
    print(f'matched {hit}/{len(res)}; missing: {miss}')
    if '--write' in sys.argv:
        if miss:
            sys.exit('not writing: unmatched records')
        bak = WIKI.replace('.json', time.strftime('.backup-%Y%m%dT%H%M%S.json'))
        shutil.copy2(WIKI, bak)
        with open(WIKI, 'w', encoding='utf-8') as f:
            json.dump(wiki, f, indent=1, ensure_ascii=False)
        print('backup', bak, '-> wrote', WIKI)


if __name__ == '__main__':
    main()
