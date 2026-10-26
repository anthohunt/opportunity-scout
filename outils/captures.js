// Captures de l'app en ligne après connexion (Playwright) et du mail du lundi rendu.
// Usage : MDP=... NODE_PATH=<node_modules avec playwright> node captures.js <dossier de sortie> [mail.html]
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2], mail = process.argv[3];
  const browser = await chromium.launch({executablePath: process.env.CHROME});
  for (const [w, h] of [[1280, 900], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: w < 500 ? 2 : 1 });
    const page = await ctx.newPage();
    await page.goto('(process.env.APP_URL || 'http://localhost:8000') + '/login'');
    await page.fill('input[name=password]', process.env.MDP);
    await page.click('button.primary');
    await page.waitForURL('**/pistes');
    await page.waitForTimeout(3000);
    const n = await page.locator('.card').count();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    await page.screenshot({ path: `${out}/pistes-${w}.png`, fullPage: true });
    console.log(`${w}px : ${n} pistes, débordement horizontal : ${overflow}`);
    await ctx.close();
  }
  if (mail) {
    const ctx = await browser.newContext({ viewport: { width: 700, height: 900 } });
    const page = await ctx.newPage();
    await page.goto('file://' + mail);
    await page.screenshot({ path: `${out}/mail-lundi.png`, fullPage: true });
    console.log('mail capturé');
  }
  await browser.close();
})();
