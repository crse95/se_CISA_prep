"""Apply the 2026-10-25 verification results to the CISA wiki JSON.

Inputs (this folder): sybex_check_results.json (book check) and web_check_results.json
(primary-source check). Per matched record it sets:
  sybex_check  {status, label, note, checked} + book_refs   (third-party book support)
  verification {status, source_type, url, evidence, note, checked}  (online primary source)
verified -> basis "sourced", URL added (source_url if empty, else source_urls), flag removed.
partial / not_verified / conflict -> flag kept and reworded. Also updates matching
unverified_items, adds new URLs to meta.link_check.url_status, and fixes three record
texts that said a fact was unsourced. Idempotent. Dry run by default; --write backs up first.
"""
import json, os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
WIKI = os.path.join(HERE, '..', 'CISA exam domains wiki.json')
DAY = '2026-10-25'
FLAG = 'No source URL; claim needs a source.'


def load(n):
    return json.load(open(os.path.join(HERE, n), encoding='utf-8'))


def index(wiki):
    idx = {}
    for g in wiki['glossary']:
        idx[('glossary', g.get('term'))] = g
    for d in wiki['domains']:
        for t in d.get('exam_traps', []):
            idx[('exam_trap', d['id'], t.get('confused_concepts'))] = t
    for t in wiki['cross_domain_themes']:
        idx[('theme', t.get('theme'))] = t
    return idx


def key(r):
    if r['kind'] == 'glossary':
        return ('glossary', r['term'])
    if r['kind'] == 'theme':
        return ('theme', r['theme'])
    return ('exam_trap', r['domain'], r['confused_concepts'])


def add_url(rec, kind, url):
    if not url:
        return
    if not rec.get('source_url'):
        rec['source_url'] = url
        return
    if rec['source_url'] == url:
        return
    field = 'additional_source_urls' if kind == 'theme' else 'source_urls'
    lst = rec.setdefault(field, [])
    if url not in lst:
        lst.append(url)


def main():
    wiki = json.load(open(WIKI, encoding='utf-8'))
    book, web = load('sybex_check_results.json'), load('web_check_results.json')
    idx, miss, counts = index(wiki), [], {}
    for r in book:
        rec = idx.get(key(r))
        if rec is None:
            miss.append(key(r)); continue
        rec['sybex_check'] = {'status': r['status'], 'label': r['label'], 'note': r['note'], 'checked': DAY}
        if r['book_refs']:
            rec['book_refs'] = r['book_refs']
    for r in web['records']:
        rec = idx.get(key(r))
        if rec is None:
            miss.append(key(r)); continue
        counts[r['status']] = counts.get(r['status'], 0) + 1
        rec['verification'] = {k: r[k] for k in ('status', 'source_type', 'url', 'evidence', 'note') if r.get(k)}
        rec['verification']['checked'] = DAY
        add_url(rec, r['kind'], r.get('url'))
        if r['status'] == 'verified':
            rec['basis'] = 'sourced'
            rec.pop('flag', None)
        elif rec.get('flag') or not rec.get('source_url'):
            rec['flag'] = {'partial': 'Partly verified; see verification note.',
                           'conflict': 'ISACA glossary disagrees; see verification note.',
                           'not_verified': FLAG}[r['status']]
    # unverified_items
    items = wiki['unverified_items']
    for pre, status, reason, action, url, st in web['unverified_items']:
        hits = [u for u in items if u.get('item', '').startswith(pre)]
        if pre == 'YouTube candidate':
            hits = [u for u in hits if 'bot check' in u.get('reason', '')]
        if not hits:
            miss.append(('item', pre)); continue
        for u in hits:
            if pre == 'YouTube candidate':
                if 'Retried 2026-10-25' not in u['reason']:
                    u['reason'] += ' ' + reason
                continue
            u.update({'status': status, 'reason': reason, 'needed_action': action})
            if url:
                u['source_url'], u['source_type'] = url, st
    tally = {}
    for r in web['records']:
        tally[r['status']] = tally.get(r['status'], 0) + 1
    for u in items:
        it = u.get('item', '')
        if it.startswith('Glossary entries marked unverified_paraphrase'):
            u.update({'status': 'resolved' if not tally.get('not_verified') and not tally.get('conflict') else 'open',
                      'reason': f'Checked {DAY} against the ISACA glossary (isaca.org/resources/glossary now loads), NIST and IEC: '
                                f'{tally.get("verified", 0)} verified, {tally.get("partial", 0)} partly, {tally.get("not_verified", 0)} not verified, '
                                f'{tally.get("conflict", 0)} conflict (Detection risk), across 35 glossary terms, 4 traps and 1 theme. Each record has a verification field.',
                      'needed_action': 'Review the partial, not-verified and conflict records.'})
        for k, r in [(('exam_trap', 'D4', 'SDO vs RTO'), 'D4 exam trap: SDO vs RTO'), (('glossary', 'Service delivery objective (SDO)'), 'Glossary: Service delivery objective (SDO)'),
                     (('exam_trap', 'D2', 'Data owner vs data custodian'), 'D2 exam trap: Data owner vs data custodian'), (('exam_trap', 'D4', 'ISO/IEC 27031 vs BCMS'), 'D4 exam trap: ISO/IEC 27031 vs BCMS'),
                     (('exam_trap', 'D5', 'FAR vs FRR vs CER'), 'D5 exam trap: FAR vs FRR vs CER'), (('theme', 'CISM 2026 update is not a CISA update'), 'Theme: CISM 2026 update is not a CISA update')]:
            if it == r:
                v = idx[k]['verification']
                u.update({'status': 'resolved' if v['status'] == 'verified' else 'open',
                          'reason': f'{v["status"]} ({DAY}): {v.get("note") or v.get("evidence")}',
                          'needed_action': 'None.' if v['status'] == 'verified' else 'Find a primary source for the unverified part or drop it.'})
    # url_status for every new URL
    us = wiki['meta']['link_check']['url_status']
    for u, (s, n) in web['extra_urls'].items():
        us.setdefault(u, {'status': s, 'note': n})
    for pre, status, reason, action, url, st in web['unverified_items']:
        if url and url not in us:
            us[url] = {'status': 'ok', 'note': f'Loads {DAY}. ' + reason[:200]}
    for r in web['records']:
        if r.get('url') and r['url'] not in us:
            us[r['url']] = {'status': 'ok', 'note': f'Loads {DAY}; quoted in record verification fields.'}
    # record texts that said these facts were unsourced
    d = {x['id']: x for x in wiki['domains']}
    iia = 'https://www.theiia.org/en/group-services/quality-assurance/quality-services/qaip/'
    for s in d['D1']['subtopics']:
        if s.get('name') == 'Quality Assurance and Improvement of the Audit Process':
            s['exam_distinctions'] = [x.replace("(an IIA 'at least every 5 years' figure is from training knowledge and was NOT confirmed in this research)",
                                                "(IIA GIAS Standard 8.4: external assessment at least once every five years)") for x in s.get('exam_distinctions', [])]
            if iia not in s.setdefault('source_urls', []):
                s['source_urls'].append(iia)
    sun = 'https://www.crowdstrike.com/en-us/blog/sunspot-malware-technical-analysis/'
    ms = 'https://blogs.microsoft.com/blog/2024/07/20/helping-our-customers-through-the-crowdstrike-outage/'
    for dom in wiki['domains']:
        for x in dom.get('real_world_examples', []):
            if x.get('name', '').startswith('SolarWinds Orion'):
                x['what_happened'] = x['what_happened'].replace('The build-server injection mechanism (SUNSPOT) is background knowledge not sourced in this research.',
                                                                'CrowdStrike found that the SUNSPOT implant watched for Orion builds and swapped one source file for one containing the SUNBURST backdoor.')
                if sun not in x.setdefault('additional_source_urls', []):
                    x['additional_source_urls'].append(sun)
            if x.get('name', '').startswith('CrowdStrike Falcon'):
                if ms not in x.setdefault('additional_source_urls', []):
                    x['additional_source_urls'].append(ms)
    # stale notes contradicted by the 2026-10-24/25 checks (exact string replacements)
    fixes = [('SP 800-218 Rev. 1 (SSDF v1.2) listed as a draft dated 17 Dec 2025; final status as of Oct 2026 not confirmed',
              'SP 800-218 Rev. 1 (SSDF v1.2) is still an Initial Public Draft on 2026-10-25 (CSRC; comments closed 30 Jan 2026; no final page)'),
             ('URL was tried and failed DNS; it was NOT confirmed in search results', 'CSRC page loads (link check 2026-10-24)'),
             ('tried, fetch failed; not confirmed in search results', 'CSRC page loads (link check 2026-10-24)'),
             ('OWASP Top 10:2025 (release candidate)', 'OWASP Top 10:2025 (final release; top10.owasp.org, 2026-10-25)'),
             ('the OWASP Top 10:2025 release candidate', 'the OWASP Top 10:2025 (final release)')]
    def fix(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str):
                    for a, b in fixes:
                        v = v.replace(a, b)
                    o[k] = v
                else:
                    fix(v)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if isinstance(v, str):
                    for a, b in fixes:
                        v = v.replace(a, b)
                    o[i] = v
                else:
                    fix(v)
    fix(wiki['domains'])
    for u, t in [(sun, 'vendor'), (ms, 'primary (company)')]:
        us.setdefault(u, {'status': 'ok', 'note': f'Loads {DAY}.'})
    print('records by status:', counts, '| missing:', miss)
    if '--write' in sys.argv:
        if miss:
            sys.exit('not writing: unmatched entries')
        bak = WIKI.replace('.json', time.strftime('.backup-%Y%m%dT%H%M%S.json'))
        shutil.copy2(WIKI, bak)
        with open(WIKI, 'w', encoding='utf-8') as f:
            json.dump(wiki, f, indent=1, ensure_ascii=False)
        print('backup', bak, '-> wrote', WIKI)


if __name__ == '__main__':
    main()
