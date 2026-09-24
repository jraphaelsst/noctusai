// Intercept window.open to learn where a button goes WITHOUT opening a tab.
// Set LABEL to the exact button text, run, read the result. Digits masked.
// Only use on buttons already known to be navigation (never on a write control).
const LABEL = 'Acessar anúncio';
window.__opened = [];
window.open = function (u, t) { window.__opened.push(String(u).replace(/\d{6,}/g, 'ID').split('?')[0] + ' target=' + t); return null; };
const btn = [...document.querySelectorAll('main button, main a')].find((b) => b.innerText.trim() === LABEL);
if (btn) btn.click();
await new Promise((r) => setTimeout(r, 2000));
JSON.stringify({ found: !!btn, opened: window.__opened });
