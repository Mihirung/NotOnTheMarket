// Load the built page in a headless browser and report what it shows and anything that failed.
//   node web/check_page.js <url> [screenshot.png]
// Prints the start of the results page's text, then a JSON list of failed requests, HTTP errors and
// script errors: [] is a clean run. Used by check_page.sh.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined, args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const bad = [];
  p.on('requestfailed', r => bad.push('FAILED ' + r.url().slice(0, 120)));
  p.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url().slice(0, 120)); });
  p.on('pageerror', e => bad.push('PAGEERROR ' + String(e).slice(0, 200)));
  await p.goto(process.argv[2] + '#/results', { waitUntil: 'load' });
  await p.waitForTimeout(3000);
  const t = await p.evaluate(() => document.body.innerText);
  console.log(t.replace(/\s+/g, ' ').slice(0, 700));
  const foot = await p.evaluate(() => (document.getElementById('footasof') || {}).textContent || '');
  console.log('AS OF: ' + foot);
  if (process.argv[3]) await p.screenshot({ path: process.argv[3] });
  console.log(JSON.stringify(bad));
  await b.close();
  process.exit(bad.length ? 1 : 0);
})();
