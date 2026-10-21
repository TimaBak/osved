/* Real Chromium UI smoke, run against https://osved.tima.biz after deploy.
 * The API login and owner data are MOCKED to test UI only. The public API is
 * separately asserted to return 401 without a session in the parent workflow.
 */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 1,
    });
    page.on("pageerror", error => { throw error; });
    await page.goto("https://osved.tima.biz/", {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.locator("#login-state").waitFor({ state: "visible" });
    await page.waitForTimeout(1300);
    assert.equal(await page.locator("#login-code").isVisible(), true);
    assert.equal(await page.locator("#auth").isVisible(), true);
    // The exact bug reported by the owner: private dashboard was visible
    // BELOW the login due to author CSS overriding the [hidden] attribute.
    assert.equal(
      await page.locator("#shell").evaluate(node => getComputedStyle(node).display),
      "none",
      "Private dashboard must be visually hidden before authentication",
    );
    await page.route("**/api/code-login", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, csrf: "frontend-smoke-token" }),
    }));
    let editorialReady = true;
    await page.route("**/api/overview", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        feed: editorialReady ? [
          { kind: "news", id: 1, title: "Проверенный пример",
            summary: "Редакционный материал", saved: false,
            url: "https://example.org/article" },
        ] : [],
        radar: [
          { id: 2, title: "Предварительный сигнал",
            source: "Пример источника", verified: false,
            url: "https://example.org/" },
        ],
        sources: [
          { id: "rss:example.org", name: "Источник RSS",
            kind: "rss", enabled: true },
        ],
        health: { status: "ok", news_24h: 1, last_news_at: null },
      }),
    }));
    await page.route("**/api/source", route => route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ id: "rss:example.org", enabled: false }),
    }));
    await page.route("**/api/logout", route => route.fulfill({
      status: 200, contentType: "application/json", body: '{"ok":true}',
    }));
    await page.locator("#login-code").fill("123456789012");
    await page.locator("#code-login-submit").click();
    await page.locator("#shell").waitFor({ state: "visible", timeout: 7000 });
    assert.equal(await page.locator("#auth").isVisible(), false);
    await page.locator('[data-section="radar"]').click();
    await page.getByText("Предварительный сигнал").waitFor({state:"visible"});
    await page.locator('[data-section="sources"]').click();
    await page.getByText("Источник RSS").waitFor({state:"visible"});
    await page.getByRole("button", { name: "Приостановить" }).click();
    await page.getByText("ПАУЗА").waitFor({state:"visible"});
    await page.locator('[data-section="feed"]').click();
    await page.getByText("Проверенный пример").waitFor({state:"visible"});
    // Verify the genuine raw-signal fallback is usable when no news passed
    // the evidence gates, rather than displaying an inert empty page.
    editorialReady = false;
    await page.locator("#refresh").click();
    await page.getByText("СИГНАЛЫ ИСТОЧНИКОВ · НЕПРОВЕРЕННЫЕ").waitFor({state:"visible"});
    await page.getByText("Предварительный сигнал").waitFor({state:"visible"});
    await page.locator("#logout").click();
    await page.locator("#auth").waitFor({state:"visible"});
    assert.equal(await page.locator("#shell").isVisible(), false);
    console.log("PASS: real CSS visibility, browser code login, navigation, source toggle, logout.");
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
