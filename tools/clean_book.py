#!/usr/bin/env python3
"""Clean boilerplate and OCR artifacts from the scanned CISA practice-exam book.

Core Python only. The input file is never modified.

Usage:
  python3 clean_book.py IN.md OUT.md LOG.jsonl                # full run
  python3 clean_book.py IN.md OUT.md LOG.jsonl --range 1:1100 # subset (1-based, inclusive)
  python3 clean_book.py ... --no-repair                       # boilerplate only, skip OCR repairs

Every change is written to LOG.jsonl (one JSON object per change) with the rule,
the original 1-based line number and the before/after text, so it can be audited
or reversed. A per-rule summary is printed to stdout.

Rules
  Boilerplate (removal):
    cover          duplicated OCR of the front/back cover before the title page
    title_cities   publisher city list on the title page
    legal          copyright, trademark, disclaimer, terms of use, dedication;
                   keeps ISBN/MHID lines and the first sentence of the copyright line
    toc            "Contents at a glance" and "Contents" (redundant with headings)
    acknowledgments
    appendix       online-content appendix: license, product key, support, publisher ads
    icon_image     image placeholder that is only the NOTE/CAUTION/TIP icon
  Formatting (no content removed):
    heading_glyph  OCR'd icon letters in headings ("Q QUESTIONS", "ANSWERS A")
    chapter_label  "CHAPTER N" + "# Title" -> "# Chapter N: Title"
    page_join      paragraph split by a page break (lowercase continuation)
  OCR repair (disable with --no-repair):
    split_merged   question, option or ☑/☒ explanation glued onto the previous line
    answer_marker  ☑/☒/☐ normalized: "X." explanation -> ☑, "X is incorrect" -> ☒
"""
import argparse
import collections
import json
import re
import sys

IMG = re.compile(r'^!\[img-\d+\.jpeg\]\(img-\d+\.jpeg\)\s*$')
ICON_NEXT = re.compile(r'^\*\*(NOTE|CAUTION|TIP|EXAM TIP)\*\*')
CITIES = re.compile(r'^(New York Chicago|Athens London|Milan New Delhi)\b')
KEEP_LEGAL = re.compile(r'^(ISBN|MHID)\b|^The material in this eBook also appears')
COPYRIGHT = re.compile(r'^(Copyright © \d{4} by [^.]+\. All rights reserved\.)')
TITLE_PAGE = re.compile(r'^# Certified Information Systems Auditor Practice Exams\s*$')
CHAPTER = re.compile(r'^CHAPTER (\d+)\s*$')
HEADING = re.compile(r'^(#+)\s+(.*)$')
# Merged-line split points: "...business.4. Michael", "sampling18. An", "...:**14.** An"
MERGED_Q = re.compile(r'(?<=[a-z.?:)”"])(\*\*)?(\d{1,2})\.(\*\*)? (?=[A-Z])')
MERGED_OPT = re.compile(r'(?<=[:?.])- (?=(\*\*)?[A-D]\.)')
MERGED_BOLD_OPT = re.compile(r'(?<=[:?])(?=\*\*[A-D]\.\*\* )')
MERGED_MARK = re.compile(r'(?<=\S)(?=[☑☒☐] )')
MARKER = re.compile(r'^(\s*- )?([☑☒☐]) ')
CORRECT = re.compile(r'^(\*\*)?[A-D](\*\*)?\.')
INCORRECT = re.compile(r'^(\*\*)?[A-D][A-D,and *]{0,20}?(\*\*)? (is|are) incorrect')


class Cleaner:
    def __init__(self, lines, offset, repair):
        # lines: list of (orig_lineno, text)
        self.lines = lines
        self.offset = offset
        self.repair = repair
        self.log = []
        self.notes = []

    def record(self, rule, lineno, before, after=None):
        self.log.append({'rule': rule, 'line': lineno, 'before': before, 'after': after})

    def find(self, pred, start=0):
        for i in range(start, len(self.lines)):
            if pred(self.lines[i][1]):
                return i
        return None

    def drop_range(self, rule, a, b, keep=None):
        """Drop lines [a, b). keep(text) -> None to drop, or replacement text to keep."""
        out = []
        for i, (n, t) in enumerate(self.lines):
            if a <= i < b and t.strip():
                new = keep(t) if keep else None
                if new is None:
                    self.record(rule, n, t)
                    continue
                if new != t:
                    self.record(rule, n, t, new)
                out.append((n, new))
            elif a <= i < b:
                out.append((n, t))  # blank lines; collapsed later
            else:
                out.append((n, t))
        self.lines = out

    # ---- boilerplate -------------------------------------------------------
    def cover(self):
        title = self.find(lambda t: TITLE_PAGE.match(t))
        if title is None:
            return self.notes.append('cover: title page not in range, skipped')
        # title page starts at the "# CISA®" just above the title heading
        start = title
        for j in range(title - 1, max(title - 4, -1), -1):
            if self.lines[j][1].strip().startswith('# CISA'):
                start = j
                break
        self.drop_range('cover', 0, start)

    def title_cities(self):
        self.lines = [x for x in self.lines
                      if not (CITIES.match(x[1]) and not self.record('title_cities', *x))]

    def legal(self):
        a = self.find(lambda t: t.startswith('McGraw-Hill Education is an independent entity'))
        b = self.find(lambda t: t.strip() == '# ABOUT THE AUTHOR')
        if a is None or b is None:
            return self.notes.append('legal: anchors not in range, skipped')

        def keep(t):
            if KEEP_LEGAL.match(t):
                return t
            m = COPYRIGHT.match(t)
            return m.group(1) if m else None
        self.drop_range('legal', a, b, keep)

    def section(self, rule, start_pat, end_pat):
        a = self.find(lambda t: re.match(start_pat, t.strip()))
        if a is None:
            return self.notes.append(f'{rule}: start anchor not in range, skipped')
        b = self.find(lambda t: re.match(end_pat, t.strip()), a + 1)
        if b is None:
            return self.notes.append(f'{rule}: end anchor not in range, skipped')
        self.drop_range(rule, a, b)

    def appendix(self):
        a = self.find(lambda t: re.match(r'^-*\**APPENDIX\**\s*$', t.strip()))
        if a is None:
            return self.notes.append('appendix: anchor not in range, skipped')
        self.drop_range('appendix', a, len(self.lines))

    def icon_image(self):
        drop = set()
        for i, (n, t) in enumerate(self.lines):
            if IMG.match(t):
                j = i + 1
                while j < len(self.lines) and not self.lines[j][1].strip():
                    j += 1
                if j < len(self.lines) and ICON_NEXT.match(self.lines[j][1]):
                    drop.add(i)
                    self.record('icon_image', n, t)
        self.lines = [x for i, x in enumerate(self.lines) if i not in drop]

    # ---- formatting --------------------------------------------------------
    def heading_glyph(self):
        out = []
        for n, t in self.lines:
            new = re.sub(r'^(#+) \*\*Q QUESTIONS\*\*\s*$', r'\1 QUESTIONS', t)
            new = re.sub(r'^(#+) (\*\*)?ANSWERS A(\*\*)?\s*$', r'\1 ANSWERS', new)
            new = re.sub(r'^(#+) \*\*(QUICK ANSWER KEY|QUESTIONS|ANSWERS)\*\*\s*$', r'\1 \2', new)
            if new != t:
                self.record('heading_glyph', n, t, new)
            out.append((n, new))
        self.lines = out

    def chapter_label(self):
        out, i = [], 0
        while i < len(self.lines):
            n, t = self.lines[i]
            m = CHAPTER.match(t)
            if m:
                j = i + 1
                while j < len(self.lines) and not self.lines[j][1].strip():
                    j += 1
                h = HEADING.match(self.lines[j][1]) if j < len(self.lines) else None
                if h:
                    new = f'{h.group(1)} Chapter {m.group(1)}: {h.group(2)}'
                    self.record('chapter_label', n, t)
                    self.record('chapter_label', self.lines[j][0], self.lines[j][1], new)
                    out.append((self.lines[j][0], new))
                    i = j + 1
                    continue
            out.append((n, t))
            i += 1
        self.lines = out

    def page_join(self):
        out = []
        i = 0
        while i < len(self.lines):
            n, t = self.lines[i]
            j = i + 1
            while j < len(self.lines) and not self.lines[j][1].strip():
                j += 1
            if (j > i + 1 and j < len(self.lines) and re.search(r'[a-z,]$', t)
                    and not t.startswith('#') and re.match(r'^[a-z]', self.lines[j][1])):
                n2, t2 = self.lines[j]
                new = t + ' ' + t2
                self.record('page_join', n2, t2, new)
                self.lines[j] = (n, new)  # continue scanning the joined line
                i = j
                continue
            out.append((n, t))
            i += 1
        self.lines = out

    # ---- OCR repair --------------------------------------------------------
    def split_merged(self):
        out = []
        for n, t in self.lines:
            new = MERGED_Q.sub(lambda m: f'\n\n{m.group(2)}. ', t)
            new = MERGED_OPT.sub('\n- ', new)
            new = MERGED_BOLD_OPT.sub('\n', new)
            new = MERGED_MARK.sub('\n', new)
            if new != t:
                self.record('split_merged', n, t, new)
                for k, part in enumerate(new.split('\n')):
                    out.append((n, part))
            else:
                out.append((n, t))
        self.lines = out

    def answer_marker(self):
        out = []
        for n, t in self.lines:
            m = MARKER.match(t)
            if m:
                rest = t[m.end():]
                want = '☑' if CORRECT.match(rest) else '☒' if INCORRECT.match(rest) else None
                if want and want != m.group(2):
                    new = t[:m.start(2)] + want + t[m.end(2):]
                    self.record('answer_marker', n, t, new)
                    t = new
            out.append((n, t))
        self.lines = out

    def collapse_blanks(self):
        out = []
        for n, t in self.lines:
            if not t.strip() and out and not out[-1][1].strip():
                continue
            out.append((n, t))
        while out and not out[0][1].strip():
            out.pop(0)
        self.lines = out

    def run(self):
        self.cover()
        self.title_cities()
        self.legal()
        self.section('toc', r'^# CONTENTS AT A GLANCE$', r'^# ACKNOWLEDGMENTS$')
        self.section('acknowledgments', r'^# ACKNOWLEDGMENTS$', r'^# INTRODUCTION$')
        self.appendix()
        self.icon_image()
        self.heading_glyph()
        self.chapter_label()
        if self.repair:
            self.split_merged()
        self.page_join()
        if self.repair:
            self.answer_marker()
        self.collapse_blanks()
        return '\n'.join(t for _, t in self.lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('log')
    ap.add_argument('--range', help='a:b, 1-based inclusive line range to process')
    ap.add_argument('--no-repair', action='store_true')
    args = ap.parse_args()

    with open(args.src, encoding='utf-8') as f:
        raw = f.read().split('\n')
    if raw and raw[-1] == '':
        raw.pop()
    a, b = 1, len(raw)
    if args.range:
        a, b = (int(x) for x in args.range.split(':'))
    lines = [(i + 1, raw[i]) for i in range(a - 1, min(b, len(raw)))]

    c = Cleaner(lines, a, not args.no_repair)
    text = c.run()
    with open(args.dst, 'w', encoding='utf-8') as f:
        f.write(text)
    with open(args.log, 'w', encoding='utf-8') as f:
        for e in c.log:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')

    removed = collections.Counter(e['rule'] for e in c.log if e['after'] is None)
    changed = collections.Counter(e['rule'] for e in c.log if e['after'] is not None)
    print(f'input lines {a}-{b} ({len(lines)}), output lines {text.count(chr(10))}')
    print(f'{"rule":<16}{"removed":>8}{"changed":>9}')
    for r in sorted(set(removed) | set(changed)):
        print(f'{r:<16}{removed[r]:>8}{changed[r]:>9}')
    for note in c.notes:
        print('note:', note)


if __name__ == '__main__':
    sys.exit(main())
