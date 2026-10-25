/* Wiki side of the combined page. Runs inside the wiki frame after the wiki script.
   Shows where a domain and its subtopics sit in the study plan, and opens views/subtopics on request. */
(() => {
const TOPIC_MAP = __TOPIC_MAP__;
const post = msg => { try { window.parent.postMessage({ cisa: 1, ...msg }, '*'); } catch {} };
const main = document.getElementById('main');
const PHASES = [['learn', 'Learn'], ['practice', 'Practice'], ['review', 'Weak-area review']];
const MOCK_PHASES = [['mock', 'Mock exams'], ['mockreview', 'Mock review']];
const h = q => { const x = q / 4; return (Number.isInteger(x) ? x : x.toFixed(2).replace(/0$/, '')) + ' h'; };
const fmt = d => new Date(d + 'T00:00:00Z').toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' });
const span = p => p.from === p.to ? fmt(p.from) : `${fmt(p.from)} – ${fmt(p.to)}`;
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* wiki subtopic name -> planner topics that point at it */
const BACK = {};
for (const [d, topics] of Object.entries(TOPIC_MAP)) {
  if (d.startsWith('_')) continue;
  for (const [topic, subs] of Object.entries(topics)) {
    for (const [, name] of subs) (BACK[name] = BACK[name] || []).push({ d: +d, topic });
  }
}

let PLAN = null;
const CSS = `.plan-strip{margin-top:12px;padding:10px 12px;border:1px solid hsl(var(--border));border-left:3px solid hsl(var(--dc, var(--primary)));
  border-radius:var(--r);background:hsl(var(--card));display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center;font-size:.88rem}
.plan-strip .eyebrow{flex-basis:100%}
.plan-strip b{font-family:var(--f-mono);font-weight:500}
.plan-strip button,.pill.plan{font:500 .75rem/1.3 var(--f-mono);padding:3px 8px;border:1px solid hsl(var(--border));border-radius:var(--r);
  background:hsl(var(--muted));color:hsl(var(--primary));cursor:pointer}
.plan-strip button:hover,.pill.plan:hover{background:hsl(var(--card))}
.dcard .plan-line{font:400 .75rem/1.3 var(--f-mono);color:hsl(var(--muted-fg));margin-top:6px}
.entry.wk-hit{outline:2px solid hsl(var(--primary));outline-offset:2px;animation:wkfade 2.4s ease-out forwards}
@keyframes wkfade{80%{outline-color:hsl(var(--primary))}100%{outline-color:transparent}}`;

function strip(d) {
  const s = PLAN && PLAN.domains && PLAN.domains[d];
  const el = document.createElement('div');
  el.className = 'plan-strip'; el.dataset.bridge = '1';
  if (!PLAN) { el.innerHTML = '<span class="muted">Waiting for the planner…</span>'; return el; }
  if (PLAN.error || !s) { el.innerHTML = `<span class="eyebrow">In your study plan</span><span class="muted">${esc(PLAN.error || 'Not in the plan.')}</span>`; return el; }
  const phases = PHASES.filter(([k]) => s.phases[k]).map(([k, l]) => `<span>${l} <b>${span(s.phases[k])}</b></span>`).join('');
  el.innerHTML = `<span class="eyebrow">In your study plan</span>${phases}
    <span>Hours <b>${h(s.doneQ)} / ${h(s.plannedQ)}</b> done</span>
    ${s.next ? `<span>Next session <b>${fmt(s.next)}</b></span>` : '<span class="muted">No upcoming session</span>'}
    <button type="button" data-plan-domain="${d}">Show in planner</button>
    <button type="button" data-plan-domain="${d}" data-plan-cal="1">Show in calendar</button>`;
  return el;
}

function decorate() {
  const head = main.querySelector('.dhead[data-d]');
  if (head && !head.querySelector('.plan-strip')) {
    const d = +head.dataset.d.slice(1);
    const w = head.querySelector('.w');
    (w || head.lastElementChild).after(strip(d));
  }
  main.querySelectorAll('.dcard[data-d]').forEach(card => {
    if (card.querySelector('.plan-line') || !PLAN || !PLAN.domains) return;
    const s = PLAN.domains[+card.dataset.d.slice(1)];
    if (!s || !s.phases.learn) return;
    const p = document.createElement('div');
    p.className = 'plan-line'; p.dataset.bridge = '1';
    p.textContent = `Plan: learn ${span(s.phases.learn)} · ${h(s.doneQ)} / ${h(s.plannedQ)}`;
    card.appendChild(p);
  });
  main.querySelectorAll('.entry').forEach(art => {
    if (art.dataset.wk) return;
    art.dataset.wk = '1';
    const h3 = art.querySelector('.ehead h3');
    if (!h3) return;
    const name = h3.textContent.replace(/^[A-Z]\.\s*/, '').trim();
    const refs = BACK[name];
    if (!refs) return;
    art.dataset.sub = name;
    const head = art.querySelector('.ehead');
    refs.forEach(r => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'pill plan'; b.dataset.planDomain = r.d;
      b.title = 'Planner key topic in Domain ' + r.d + '. Click to show it in the planner.';
      b.textContent = `Plan: D${r.d} · ${r.topic}`;
      head.appendChild(b);
    });
  });
}
function redecorate() {
  main.querySelectorAll('[data-bridge]').forEach(n => n.remove());
  main.querySelectorAll('.entry[data-wk]').forEach(a => { delete a.dataset.wk; a.querySelectorAll('.pill.plan').forEach(n => n.remove()); });
  decorate();
}

let busy = false;
new MutationObserver(() => { if (busy) return; busy = true; try { decorate(); } finally { busy = false; } })
  .observe(main, { childList: true });

document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-plan-domain]');
  if (!b) return;
  ev.preventDefault();
  post({ type: 'show-in-planner', domain: +b.dataset.planDomain, calendar: !!b.dataset.planCal });
});

/* ---------- requests from the shell ---------- */
function clearFilters() {
  const reset = document.querySelector('#chips [data-reset]');
  if (reset) reset.click();
}
function openView(view, subtopics) {
  clearFilters();
  if (location.hash.slice(1) !== view) location.hash = view;
  else window.scrollTo(0, 0);
  if (!subtopics || !subtopics.length) return;
  let tries = 0;
  const find = () => {
    const arts = [...main.querySelectorAll('.entry[data-sub]')].filter(a => subtopics.includes(a.dataset.sub));
    if (!arts.length) { if (++tries < 30) setTimeout(find, 50); return; }
    arts[0].scrollIntoView({ block: 'start' }); window.scrollBy(0, -130);
    arts.forEach(a => { a.classList.remove('wk-hit'); void a.offsetWidth; a.classList.add('wk-hit'); });
  };
  setTimeout(find, 30);
}
window.addEventListener('message', ev => {
  if (ev.source !== window.parent || !ev.data || ev.data.cisa !== 1) return;
  const m = ev.data;
  if (m.type === 'plan') { PLAN = m.summary; redecorate(); }
  if (m.type === 'open' && typeof m.view === 'string') openView(m.view, m.subtopics);
});

const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
decorate();
post({ type: 'ready', frame: 'wiki' });
})();
