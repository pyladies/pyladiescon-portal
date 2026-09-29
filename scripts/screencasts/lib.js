const { chromium } = require("playwright-core");
const path = require("path");

const CONFIG = {
  base: process.env.BASE_URL || "http://127.0.0.1:8002",
  maildev: process.env.MAILDEV_URL || "http://localhost:1080",
  password: process.env.SAMPLE_PASSWORD || "password123",
  headshot: process.env.HEADSHOT || path.join(__dirname, "out", "headshot.jpg"),
  // Leave unset to use the browser Playwright installed (npx playwright install chromium).
  chrome: process.env.PLAYWRIGHT_CHROME || undefined,
  // A smaller viewport makes text larger relative to the video frame. Keep the
  // width at 992 or more so the portal stays on its desktop (lg) layout.
  width: Number(process.env.VIEWPORT_WIDTH) || 1024,
  height: Number(process.env.VIEWPORT_HEIGHT) || 640,
};

const OVERLAY = `
(() => {
  const boot = () => {
    if (document.getElementById('__cur')) return;
    const st = document.createElement('style');
    st.textContent = \`
      #__cur{position:fixed;z-index:2147483647;width:22px;height:22px;pointer-events:none;left:0;top:0;
        transform:translate(-4px,-2px);transition:none}
      #__cur svg{filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))}
      .__rip{position:fixed;z-index:2147483646;width:14px;height:14px;border-radius:50%;
        border:3px solid #e0344f;pointer-events:none;transform:translate(-50%,-50%);
        animation:__rip .6s ease-out forwards}
      @keyframes __rip{to{width:56px;height:56px;opacity:0}}
      #__cap{position:fixed;z-index:2147483647;left:0;right:0;bottom:0;padding:12px 24px;
        background:rgba(24,30,50,.92);color:#fff;font:600 22px/1.3 system-ui,sans-serif;text-align:center}
    \`;
    document.head.appendChild(st);
    const c = document.createElement('div'); c.id='__cur';
    c.innerHTML='<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2l14 8-6 2 3 7-3 1-3-7-5 4z" fill="#fff" stroke="#111" stroke-width="1.4"/></svg>';
    document.body.appendChild(c);
    let x = +sessionStorage.getItem('__x')||40, y = +sessionStorage.getItem('__y')||40;
    c.style.left = x+'px'; c.style.top = y+'px';
    window.__moveCursor = (nx, ny) => { c.style.left=nx+'px'; c.style.top=ny+'px';
      sessionStorage.setItem('__x',nx); sessionStorage.setItem('__y',ny); };
    window.__ripple = (nx, ny) => { const r=document.createElement('div'); r.className='__rip';
      r.style.left=nx+'px'; r.style.top=ny+'px'; document.body.appendChild(r); setTimeout(()=>r.remove(),700); };
    window.__caption = (t) => { let e=document.getElementById('__cap');
      if(!t){ if(e) e.remove(); sessionStorage.removeItem('__capt'); return; }
      if(!e){ e=document.createElement('div'); e.id='__cap'; document.body.appendChild(e); }
      e.textContent=t; sessionStorage.setItem('__capt',t); };
    const saved = sessionStorage.getItem('__capt'); if (saved) window.__caption(saved);
  };
  if (document.body) boot(); else document.addEventListener('DOMContentLoaded', boot);
})();
`;

async function launch({ record, name }) {
  const browser = await chromium.launch({ executablePath: CONFIG.chrome, headless: true });
  const opts = { viewport: { width: CONFIG.width, height: CONFIG.height }, deviceScaleFactor: 1, locale: "en-US" };
  if (record) opts.recordVideo = { dir: record, size: { width: CONFIG.width, height: CONFIG.height } };
  const context = await browser.newContext(opts);
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();
  return { browser, context, page };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function caption(page, text) {
  await page.evaluate((t) => window.__caption && window.__caption(t), text);
}

async function moveTo(page, x, y) {
  const from = await page.evaluate(() => [
    +sessionStorage.getItem("__x") || 40,
    +sessionStorage.getItem("__y") || 40,
  ]);
  const steps = 14;
  for (let i = 1; i <= steps; i++) {
    const nx = from[0] + ((x - from[0]) * i) / steps;
    const ny = from[1] + ((y - from[1]) * i) / steps;
    await page.evaluate(([a, b]) => window.__moveCursor && window.__moveCursor(a, b), [nx, ny]);
    await sleep(22);
  }
}

async function click(page, target, { pause = 700 } = {}) {
  const loc = typeof target === "string" ? page.locator(target).first() : target;
  await loc.scrollIntoViewIfNeeded();
  const box = await loc.boundingBox();
  const x = box.x + Math.min(box.width / 2, 120);
  const y = box.y + box.height / 2;
  await moveTo(page, x, y);
  await page.evaluate(([a, b]) => window.__ripple && window.__ripple(a, b), [x, y]);
  await sleep(150);
  await loc.click();
  await sleep(pause);
}

async function type(page, target, text, { delay = 28 } = {}) {
  const loc = typeof target === "string" ? page.locator(target).first() : target;
  await click(page, loc, { pause: 150 });
  await loc.pressSequentially(text, { delay });
  await sleep(250);
}

async function choose(page, selectSelector, label) {
  const loc = page.locator(selectSelector).first();
  await loc.scrollIntoViewIfNeeded();
  const box = await loc.boundingBox();
  await moveTo(page, box.x + 60, box.y + box.height / 2);
  await page.evaluate(([a, b]) => window.__ripple && window.__ripple(a, b), [box.x + 60, box.y + box.height / 2]);
  await sleep(200);
  await loc.selectOption({ label });
  await sleep(600);
}

async function login(page, username, password, { landing = "/accounts/login/" } = {}) {
  await page.goto(CONFIG.base + landing);
  await type(page, 'input[name="login"]', username);
  await type(page, 'input[name="password"]', password);
  await click(page, 'button:has-text("Sign In")', { pause: 1200 });
}

async function shot(page, file) {
  await page.screenshot({ path: file });
}

module.exports = { CONFIG, launch, sleep, caption, click, type, choose, login, moveTo, shot, path };
