/* Planner side of the combined page. Runs inside the planner frame, before the planner bundle.
   Reads the plan through window.__cisaPlanHook (one patched line in the bundle), posts a summary to the
   shell, and adds "wiki" links to the day panel and the domain drill-down. Never edits the planner's state. */
(() => {
const TOPIC_MAP = __TOPIC_MAP__;
const post = msg => { try { window.parent.postMessage({ cisa: 1, ...msg }, '*'); } catch {} };
const DIDS = [1, 2, 3, 4, 5];

function summarize(plan, today) {
  if (!plan || plan.error) return { error: plan ? plan.error : 'no plan', today };
  const dom = {};
  const slot = k => dom[k] || (dom[k] = { phases: {}, plannedQ: 0, doneQ: 0, next: null });
  plan.queue.forEach(u => { slot(u.domain == null ? 'mock' : u.domain).plannedQ += u.q; });
  const add = (date, sessions, done) => (sessions || []).forEach(s => {
    const o = slot(s.domain == null ? 'mock' : s.domain);
    const ph = o.phases[s.phase] || (o.phases[s.phase] = { from: date, to: date, q: 0 });
    if (date < ph.from) ph.from = date;
    if (date > ph.to) ph.to = date;
    ph.q += s.q;
    if (done) o.doneQ += s.q;
    else if (date >= today && (!o.next || date < o.next)) o.next = date;
  });
  Object.entries(plan.done || {}).forEach(([d, ss]) => add(d, ss, true));
  plan.projection.days.forEach(day => add(day.date, day.sessions, false));
  const upcoming = plan.projection.days.filter(d => d.date >= today && d.q > 0).slice(0, 1)
    .map(d => ({ date: d.date, sessions: d.sessions.map(s => ({ domain: s.domain, phase: s.phase, q: s.q })) }));
  return { today, end: plan.projection.end, examDate: plan.examDate, domains: dom, upcoming };
}

let last = null;
window.__cisaPlanHook = (plan, today) => { last = summarize(plan, today); post({ type: 'plan', summary: last }); };

/* ---------- links into the wiki ---------- */
const CSS = `.wk-link{display:inline-flex;align-items:center;gap:4px;font:500 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  padding:1px 6px;margin-left:6px;border:1px solid hsl(var(--border));border-radius:2px;background:hsl(var(--card));
  color:hsl(var(--primary));cursor:pointer;white-space:nowrap;vertical-align:baseline}
.wk-link:hover{background:hsl(var(--muted))}
.wk-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px;color:hsl(var(--muted-foreground))}
.wk-row .wk-link{margin-left:0}
.wk-flash{animation:wkflash 1.6s ease-out}
@keyframes wkflash{0%{box-shadow:0 0 0 3px hsl(var(--primary))}100%{box-shadow:0 0 0 0 hsl(var(--primary)/0)}}`;

function linkBtn(label, msg, title) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'wk-link'; b.dataset.bridge = '1';
  b.textContent = label + ' ↗'; if (title) b.title = title;
  b.addEventListener('click', ev => { ev.stopPropagation(); ev.preventDefault(); post({ type: 'open-wiki', ...msg }); });
  return b;
}

function decorateDay() {
  const ul = document.querySelector('[data-testid=day-sessions]');
  if (!ul) return;
  const doms = new Set(); let mock = false;
  ul.querySelectorAll('li').forEach(li => {
    const m = li.textContent.match(/\bD([1-5])\b/);
    if (m) doms.add(+m[1]); else if (/mock/i.test(li.textContent)) mock = true;
  });
  const key = [...doms].join(',') + (mock ? 'm' : '');
  let row = ul.parentElement.querySelector(':scope > .wk-row');
  if (row && row.dataset.key === key) return;
  if (row) row.remove();
  if (!key) return;
  row = document.createElement('div');
  row.className = 'wk-row'; row.dataset.bridge = '1'; row.dataset.key = key;
  row.append('Study material:');
  doms.forEach(d => row.append(linkBtn(`D${d} in wiki`, { view: 'D' + d }, 'Open this domain in the wiki')));
  if (mock) row.append(linkBtn('Key facts', { view: 'facts' }, 'Open key facts in the wiki'));
  ul.after(row);
}

function activeDrill() {
  const b = document.querySelector('[data-testid=drilldown] button[id^=drill-d][aria-pressed=true]');
  return b ? +b.id.slice(7) : null;
}
function decorateDrill() {
  const box = document.querySelector('[data-testid=drilldown]');
  if (!box) return;
  const d = activeDrill();
  if (!d) return;
  const map = TOPIC_MAP[d] || {};
  box.querySelectorAll('li').forEach(li => {
    if (li.querySelector('.wk-link')) return;
    const spans = li.querySelectorAll(':scope > span');
    const topic = spans.length ? spans[spans.length - 1].textContent.trim() : '';
    const subs = map[topic];
    if (!subs) return;
    const view = subs[0][0];
    li.append(linkBtn('wiki', { view, subtopics: subs.map(s => s[1]) },
      'Wiki: ' + subs.map(s => `${s[0]} ${s[1]}`).join('; ')));
  });
  const cal = document.getElementById('show-in-calendar');
  if (cal) {
    const old = cal.parentElement.querySelector(':scope > .wk-domain');
    if (old && old.dataset.d === String(d)) return;
    if (old) old.remove();
    const b = linkBtn(`Open D${d} in wiki`, { view: 'D' + d });
    b.classList.add('wk-domain'); b.dataset.d = String(d);
    b.style.cssText = 'font-size:13px;padding:6px 12px;margin-left:8px;align-self:flex-start';
    cal.after(b);
  }
}

let busy = false;
function decorate() {
  if (busy) return;
  busy = true;
  try { decorateDay(); decorateDrill(); } finally { busy = false; }
}

/* ---------- requests from the shell ---------- */
const tick = () => new Promise(r => setTimeout(r, 60));
async function showDomain(d) {
  document.getElementById('tab-domains')?.click(); await tick();
  document.getElementById('drill-d' + d)?.click(); await tick();
  const box = document.querySelector('[data-testid=drilldown]');
  if (box) { box.scrollIntoView({ block: 'start', behavior: 'smooth' }); box.classList.add('wk-flash'); setTimeout(() => box.classList.remove('wk-flash'), 1700); }
}
async function showCalendar(d) {
  await showDomain(d);
  document.getElementById('show-in-calendar')?.click();
}
window.addEventListener('message', ev => {
  if (ev.source !== window.parent || !ev.data || ev.data.cisa !== 1) return;
  const m = ev.data;
  if (m.type === 'show-domain' && DIDS.includes(m.domain)) (m.calendar ? showCalendar : showDomain)(m.domain);
  if (m.type === 'hello' && last) post({ type: 'plan', summary: last });
});

document.addEventListener('DOMContentLoaded', () => {
  const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
  const root = document.getElementById('root');
  if (root) new MutationObserver(decorate).observe(root, { childList: true, subtree: true, characterData: true });
  decorate();
  post({ type: 'ready', frame: 'planner' });
});
})();
