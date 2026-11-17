"""First-session spotlight tour for Flyover (plan feature 7).

The tour dims the page, rings one control at a time, points an arrow at it and explains it in
a callout with Back / Next / Skip. It only explains: it never generates a profile, calls the
model, resolves or completes anything.

How it runs: Streamlit draws scripts inside a helper frame that it removes on the next redraw,
which would stop a tour mid-way. So the frame only copies the tour's code into the page itself
(a <script> in the parent document), where it keeps running across Streamlit redraws until the
student finishes or skips it. "Seen" is remembered for the browser tab in sessionStorage;
Settings → Replay tutorial starts it again.

Targets are Streamlit's stable `st-key-…` classes from keyed widgets and containers, never
screen positions. A target that isn't on the page is skipped rather than pointed at.
"""

import json

# (CSS selector, title, explanation, shape). 'circle' for small controls, 'rounded' for wide.
TOUR_STEPS = [
    ('.st-key-flyover_profile', 'Start with your profile',
     ('Choose your school, arrival date and whether you have an SSN (yes or no only). '
     'Never enter your name or document numbers.'), 'rounded'),
    ('.st-key-flyover_profile [data-testid="stFormSubmitButton"]', 'Generate your workflow',
     ('Flyover builds your steps from official sources. Starting over asks first if you '
     'already have progress.'), 'rounded'),
    ('.st-key-flyover_gate', 'One step at a time',
     ('This is the step to do now, most important first. Set Status to In Progress while you '
     "wait on an office, and Completed when it's done. Completion is self-reported."), 'rounded'),
    ('.st-key-flyover_checklist', 'Open the checklist',
     ('See the documents to bring and visit details with their sources. "Not verified" means '
     'confirm with the office. A blocked step has Resolve blocker, which drafts an email you '
     'review and send yourself.'), 'rounded'),
    ('.st-key-flyover_ai', 'Ask AI Help',
     ("Ask about the step you're on. Answers come from your workflow and our sources. Don't "
     'include your name, SSN or document numbers.'), 'circle'),
    ('.st-key-flyover_next', 'Readiness and your handoff',
     ('Next shows the step to do now and what comes after. At the bottom, a handoff for the '
     'office you visit, drafted from a template on this page.'), 'rounded'),
    ('.st-key-flyover_settings', 'Replay any time',
     'Settings has Replay tutorial, Reduce motion and Pause travel banner.', 'circle'),
]

# The tour's own look, so it doesn't depend on Streamlit's CSS. Contrast: charcoal on the
# ivory card 11.9:1, ivory on the deep-sage button 6.2:1, the ivory ring on the dimmed page.
_CSS = """
.fly-tour{position:fixed;inset:0;z-index:2147483000;font-family:Nunito,ui-rounded,system-ui,sans-serif}
.fly-tour-block{position:fixed;inset:0}
.fly-tour-hole{position:fixed;border-radius:18px;pointer-events:none;
 box-shadow:0 0 0 3px #F7F4EF,0 0 0 200vmax rgba(40,50,60,.62);transition:all .25s ease}
.fly-tour-arrow{position:fixed;width:58px;height:58px;pointer-events:none;transition:all .25s ease}
.fly-tour-card{position:fixed;width:min(360px,calc(100vw - 32px));background:#FFFDF9;color:#28323C;
 border-radius:18px;padding:18px 20px;box-shadow:0 18px 44px rgba(0,0,0,.28);transition:all .25s ease}
.fly-tour-card h2{font-family:Fredoka,Nunito,system-ui,sans-serif;font-size:1.25rem;margin:2px 0 6px;color:#28323C}
.fly-tour-card p{margin:0;font-size:.95rem;line-height:1.45}
.fly-tour-count{font-size:.72rem!important;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#57616C}
.fly-tour-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap}
.fly-tour-actions button{font:inherit;font-weight:800;border-radius:10px;padding:8px 14px;cursor:pointer;
 border:2px solid #D3DED4;background:#FFFFFF;color:#3D6350;min-height:40px}
.fly-tour-actions button.primary{background:#3D6350;border-color:#3D6350;color:#F7F4EF}
.fly-tour-actions button.skip{margin-right:auto;border-color:transparent;color:#28323C;text-decoration:underline}
.fly-tour-actions button:focus-visible{outline:3px solid #28323C;outline-offset:2px}
.fly-tour-actions button:disabled{opacity:.45;cursor:default}
.fly-tour.still .fly-tour-hole,.fly-tour.still .fly-tour-arrow,.fly-tour.still .fly-tour-card{transition:none}
"""

# Runs in the page (parent document), not in Streamlit's helper frame. __STEPS__, __REPLAY__,
# __STILL__ and __CSS__ are filled in by tour_script(); everything else is plain JavaScript.
_TOUR_JS = r"""
(function () {
  var w = window, doc = document, KEY = 'flyoverTourDone';
  var replay = __REPLAY__, steps = __STEPS__;
  try {
    if (replay) { w.sessionStorage.removeItem(KEY); }
    else if (w.sessionStorage.getItem(KEY)) { return; }
  } catch (e) {}
  if (w.__flyoverTourRunning) { return; }  // a redraw sent the script again: one tour only
  w.__flyoverTourRunning = true;
  var still = __STILL__ || (w.matchMedia && w.matchMedia('(prefers-reduced-motion: reduce)').matches);

  var style = doc.createElement('style');
  style.textContent = __CSS__;
  var root = doc.createElement('div');
  root.className = 'fly-tour' + (still ? ' still' : '');
  root.setAttribute('role', 'dialog');
  root.setAttribute('aria-modal', 'true');
  root.setAttribute('aria-labelledby', 'fly-tour-title');
  root.innerHTML = '<div class="fly-tour-block"></div><div class="fly-tour-hole"></div>' +
    '<svg class="fly-tour-arrow" viewBox="0 0 58 58" aria-hidden="true"><path d="M6 29 H46 M34 15 L48 29 L34 43" ' +
    'fill="none" stroke="#F7F4EF" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
    '<div class="fly-tour-card"><p class="fly-tour-count" aria-live="polite"></p>' +
    '<h2 id="fly-tour-title"></h2><p class="fly-tour-body"></p><div class="fly-tour-actions">' +
    '<button type="button" class="skip" data-act="skip">Skip tour</button>' +
    '<button type="button" data-act="back">Back</button>' +
    '<button type="button" class="primary" data-act="next">Next</button></div></div>';
  var app = doc.getElementById('root');
  var before = doc.activeElement, index = 0, timer = null;
  var hole = root.querySelector('.fly-tour-hole'), arrow = root.querySelector('.fly-tour-arrow');
  var card = root.querySelector('.fly-tour-card'), count = root.querySelector('.fly-tour-count');
  var title = root.querySelector('#fly-tour-title'), body = root.querySelector('.fly-tour-body');
  var back = root.querySelector('[data-act="back"]'), next = root.querySelector('[data-act="next"]');

  function target(step) {
    var el = doc.querySelector(step[0]);
    if (!el) { return null; }
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 ? el : null;  // hidden or not on this page: skip it
  }
  function available() { return steps.filter(function (s) { return target(s); }); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function place(scroll) {
    var list = available();
    if (!list.length) { return finish(); }
    index = clamp(index, 0, list.length - 1);
    var step = list[index], el = target(step), vw = w.innerWidth, vh = w.innerHeight;
    var r = el.getBoundingClientRect();
    if (scroll && (r.top < 60 || r.bottom > vh - 40)) {
      el.scrollIntoView({block: 'center', behavior: still ? 'auto' : 'smooth'});
      r = el.getBoundingClientRect();
    }
    var pad = 8, x = r.left - pad, y = r.top - pad, hw = r.width + pad * 2, hh = r.height + pad * 2;
    if (step[3] === 'circle') {
      var d = Math.max(hw, hh); x = r.left + r.width / 2 - d / 2; y = r.top + r.height / 2 - d / 2; hw = hh = d;
    }
    hole.style.left = x + 'px'; hole.style.top = y + 'px';
    hole.style.width = hw + 'px'; hole.style.height = hh + 'px';
    hole.style.borderRadius = step[3] === 'circle' ? '50%' : '18px';

    count.textContent = 'Step ' + (index + 1) + ' of ' + list.length;
    title.textContent = step[1];
    body.textContent = step[2];
    back.disabled = index === 0;
    next.textContent = index === list.length - 1 ? 'Done' : 'Next';

    // The callout goes below the target if it fits, else above; always inside the screen.
    var cw = card.offsetWidth, ch = card.offsetHeight, gap = 70;
    var below = y + hh + gap + ch < vh - 12;
    var cy = below ? y + hh + gap : Math.max(12, y - gap - ch);
    var cx = clamp(x + hw / 2 - cw / 2, 16, vw - cw - 16);
    card.style.left = cx + 'px'; card.style.top = cy + 'px';
    // The arrow sits between them and points from the callout to the target's centre.
    var tx = x + hw / 2, ty = below ? y + hh : y, ax = clamp(tx, cx + 29, cx + cw - 29);
    var ay = below ? cy - 29 - 6 : cy + ch + 6;
    var angle = Math.atan2(ty - ay - (below ? 0 : 29), tx - ax) * 180 / Math.PI;
    arrow.style.left = (ax - 29) + 'px'; arrow.style.top = (ay - (below ? 0 : 29)) + 'px';
    arrow.style.transform = 'rotate(' + angle + 'deg)';
  }

  function finish() {
    try { w.sessionStorage.setItem(KEY, '1'); } catch (e) {}
    clearInterval(timer);
    w.removeEventListener('resize', onMove);
    doc.removeEventListener('scroll', onMove, true);
    doc.removeEventListener('keydown', onKey, true);
    if (app) { app.removeAttribute('inert'); }
    root.remove(); style.remove();
    w.__flyoverTourRunning = false;
    if (before && before.focus) { try { before.focus(); } catch (e) {} }
  }
  function onMove() { place(false); }
  function onKey(event) {
    if (event.key === 'Escape') { event.preventDefault(); finish(); }
  }
  root.addEventListener('click', function (event) {
    var act = event.target && event.target.getAttribute && event.target.getAttribute('data-act');
    if (act === 'skip') { finish(); }
    else if (act === 'back') { index -= 1; place(true); }
    else if (act === 'next') {
      if (index >= available().length - 1) { finish(); } else { index += 1; place(true); }
    }
  });

  var tries = 0;
  (function start() {
    // Streamlit is still drawing on first load: wait (up to ~6 s) for the first target.
    if (!available().length && tries++ < 30) { return setTimeout(start, 200); }
    if (!available().length) { w.__flyoverTourRunning = false; return; }
    doc.head.appendChild(style);
    doc.body.appendChild(root);
    if (app) { app.setAttribute('inert', ''); }  // the page behind can't be clicked or focused
    w.addEventListener('resize', onMove);
    doc.addEventListener('scroll', onMove, true);
    doc.addEventListener('keydown', onKey, true);
    timer = setInterval(onMove, 700);  // follow Streamlit redraws that move the target
    place(true);
    next.focus();
  })();
})();
"""


def tour_code(replay: bool, reduce_motion: bool) -> str:
    """The tour's JavaScript, ready to run in the page."""
    return (_TOUR_JS.replace('__STEPS__', json.dumps(TOUR_STEPS))
            .replace('__REPLAY__', 'true' if replay else 'false')
            .replace('__STILL__', 'true' if reduce_motion else 'false')
            .replace('__CSS__', json.dumps(_CSS)))


def tour_script(replay: bool, reduce_motion: bool) -> str:
    """The helper-frame HTML: copy the tour into the page so it outlives the frame."""
    code = json.dumps(tour_code(replay, reduce_motion))
    return ('<script>(function () { var doc = window.parent.document;'
            ' var s = doc.createElement("script"); s.textContent = ' + code + ';'
            ' doc.head.appendChild(s); })();</script>')
