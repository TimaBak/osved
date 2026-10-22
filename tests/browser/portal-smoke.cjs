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
    let signedIn = false;
    await page.route("**/api/session", route => {
      if(route.request().method() !== "GET")return route.continue();
      return route.fulfill({
        status: signedIn ? 200 : 401,
        contentType:"application/json",
        body: JSON.stringify(signedIn ? {ok:true,csrf:"frontend-smoke-token"} : {error:"unauthorized"}),
      });
    });
    await page.route("**/api/code-login", route => {
      signedIn=true;
      return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, csrf: "frontend-smoke-token" }),
      });
    });
    let editorialReady = true;
    let interestPriority = 0;
    let interestAction = null;
    let addedChannel = false;
    let addedPublicSource = false;
    let hiddenNews = false;
    let bulkCalls = 0;
    await page.route("**/api/overview", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        feed: editorialReady ? [
          { kind: "news", id: 1, title: "Проверенный пример",
            summary: "Редакционный материал", saved: false,
            url: "https://example.org/article" },
        ] : [],
        hidden: hiddenNews ? [{kind:"news",id:1,hidden_at:"2026-10-22T01:00:00Z"}] : [],
        radar: [
          { id: 2, title: "Предварительный сигнал",
            source: "Пример источника", verified: false,
            url: "https://example.org/" },
        ],
        sources: [
          { id: "rss:example.org", name: "Источник RSS",
            kind: "rss", category:"Сайты и RSS", platform:"RSS / Atom",
            platform_description:"Ленты сайтов и блогов",
            topics:["ai"], status:"ready", enabled: true },
          { id:"x:example", name:"Автор X", kind:"x",
            category:"Социальные сети", platform:"X",
            topics:["research"],status:"paused",enabled:false },
        ].concat(addedChannel ? [{
          id:"youtube_user_sample",name:"YouTube — Демонстрационный канал",
          kind:"youtube",category:"Видео",platform:"YouTube",topics:[],
          enabled:true,status:"ready",
        }] : []).concat(addedPublicSource ? [{
          id:"user_github_sample",name:"GitHub — example/sample",
          kind:"github",category:"Разработка",platform:"GitHub",
          url:"https://github.com/example/sample",topics:["ai_software"],
          enabled:true,status:"ready",last_success_at:null,
        }] : []),
        health: { status: "ok", news_24h: 1, last_news_at: null },
        personalization: {
          algorithm:"heuristic_v1", feedback_count:interestAction?1:0,
          topics:[
            {id:"ai_software",title:"AI и software",priority:interestPriority},
            {id:"space",title:"Космос",priority:0},
          ],
        },
      }),
    }));
    await page.route("**/api/capabilities", route => route.fulfill({
      status: 200,contentType:"application/json",
      body:JSON.stringify({
        video:{ready:false,reason:"ai_provider_unconfigured"},
        translation:{ready:false,mode:"planned_on_demand"},
        image_ai:{ready:false},accounts:{oauth_ready:false},
      }),
    }));
    await page.route("**/api/article/news/1", route => route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({item:{
        kind:"news",id:1,title:"Проверенный пример",
        content:{brief:"<p>Полный проверенный материал <b>с первоисточником</b>.</p>"},
        sources:[{title:"Источник",url:"https://example.org/article"}],
      }}),
    }));
    await page.route("**/api/reader/news/1", route => route.fulfill({
      status: 200, contentType:"application/json",
      body: JSON.stringify({
        kind:"news",id:1,note:"Проверить независимый источник",
        is_read:true,updated_at:"2026-10-22T00:00:00Z",
      }),
    }));
    await page.route("**/api/radar/2", route => route.fulfill({
      status: 200,contentType:"application/json",
      body: JSON.stringify({item:{
        kind:"radar",id:2,title:"Предварительный сигнал",
        verified:false,content:{brief:"<p>Описание исходного сигнала</p>"},
        sources:[{title:"Первоисточник",url:"https://example.org/"}],
      }}),
    }));
    await page.route("**/api/personalization/topic", async route=>{
      const payload=route.request().postDataJSON();
      interestPriority=payload.priority;
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({ok:true,topic:payload.topic,priority:interestPriority})});
    });
    await page.route("**/api/personalization/feedback", async route=>{
      const payload=route.request().postDataJSON();
      interestAction=payload.action;
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({ok:true,topic:"ai_software",action:payload.action})});
    });
    await page.route("**/api/personalization/reset", async route=>{
      interestPriority=0;interestAction=null;
      await route.fulfill({status:200,contentType:"application/json",body:'{"ok":true}'});
    });
    await page.route("**/api/video/summary", route => route.fulfill({
      status: 409,contentType:"application/json",
      body: '{"error":"ai_provider_unconfigured"}',
    }));
    await page.route("**/api/hidden", async route=>{
      const body=route.request().postDataJSON();
      assert.equal(body.kind,"news");
      assert.equal(body.id,1);
      hiddenNews=body.hidden;
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({ok:true,...body})});
    });
    await page.route("**/api/public-sources/add", async route=>{
      const body=route.request().postDataJSON();
      assert.equal(body.kind,"github");
      assert.equal(body.locator,"example/sample");
      bulkCalls++;
      addedPublicSource=true;
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({ok:true,id:"user_github_sample",
          name:"GitHub — example/sample",existing:false})});
    });
    await page.route("**/api/public-sources/remove", async route=>{
      addedPublicSource=false;
      await route.fulfill({status:200,contentType:"application/json",
        body:'{"ok":true,"removed":true}'});
    });
    await page.route("**/api/youtube/channels/add", async route=>{
      addedChannel=true;
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({ok:true,title:"Демонстрационный канал",
          source_id:"youtube_user_sample",existing:false})});
    });
    await page.route("**/api/youtube/channels/remove", async route=>{
      addedChannel=false;
      await route.fulfill({status:200,contentType:"application/json",
        body:'{"ok":true,"removed":true}'});
    });
    await page.route("**/api/source", route => route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ id: "rss:example.org", enabled: false }),
    }));
    await page.route("**/api/logout", route => {
      signedIn=false;
      return route.fulfill({
        status:200,contentType:"application/json",body:'{"ok":true}',
      });
    });
    await page.locator("#login-code").fill("123456789012");
    await page.locator("#code-login-submit").click();
    await page.locator("#shell").waitFor({ state: "visible", timeout: 7000 });
    assert.equal(await page.locator("#auth").isVisible(), false);
    // Page refresh must resume the session, never ask for a new Telegram code.
    await page.reload({waitUntil:"domcontentloaded"});
    await page.locator("#shell").waitFor({state:"visible",timeout:7000});
    assert.equal(await page.locator("#auth").isVisible(),false);
    await page.evaluate(()=>window.scrollTo({top:750,behavior:"instant"}));
    const sticky=await page.evaluate(()=>{
      const side=document.querySelector(".sidebar").getBoundingClientRect();
      return {top:side.top,height:side.height};
    });
    assert.equal(sticky.top,0,"Mobile OSVED navigation should remain sticky");
    await page.locator('[data-section="interests"]').click();
    await page.getByText("Управление информационным потоком").waitFor({state:"visible"});
    await page.locator(".topic-tile").first().locator("button").last().click();
    await page.locator(".topic-tile").first().getByText("+1").waitFor({state:"visible"});
    assert.equal(interestPriority,1);
    await page.locator('[data-section="feed"]').click();
    await page.locator("#content .reaction-details summary").first().click();
    await page.getByRole("button",{name:"👍 Больше такого"}).first().click();
    assert.equal(interestAction,"more");
    await page.locator('[data-section="radar"]').click();
    await page.getByText("Предварительный сигнал").waitFor({state:"visible"});
    await page.locator('[data-section="sources"]').click();
    await page.getByText("Источник RSS").waitFor({state:"visible"});
    await page.getByText("Автор X").waitFor({state:"visible"});
    await page.locator("#source-platform").selectOption("Сайты и RSS");
    await page.getByText("Источник RSS").waitFor({state:"visible"});
    assert.equal(await page.getByText("Автор X").count(),0);
    await page.locator("#source-topic").selectOption("ai");
    await page.getByRole("button", { name: "Приостановить" }).click();
    await page.getByText("ПАУЗА").waitFor({state:"visible"});
    await page.locator("#source-platform").selectOption("all");
    await page.locator("#source-topic").selectOption("all");
    await page.locator("#youtube-channel-url").fill(
      "https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa");
    await page.locator("#youtube-add-form button[type=submit]").click();
    await page.getByText("Демонстрационный канал",{exact:false}).first()
      .waitFor({state:"visible"});
    assert.equal(addedChannel,true);
    await page.locator("#public-source-kind").selectOption("github");
    await page.locator("#public-source-locator").fill("example/sample");
    await page.locator("#public-source-topic").selectOption("ai_software");
    await page.locator("#public-source-add-form button[type=submit]").click();
    await page.getByText("GitHub — example/sample",{exact:true}).waitFor({state:"visible"});
    assert.equal(addedPublicSource,true);
    await page.locator("#bulk-import-text").fill(
      "https://github.com/example/sample\nhttps://vc.ru/");
    await page.locator("#bulk-import-form button").filter({hasText:"Предпросмотр"}).click();
    await page.getByText("Подключение этой площадки ещё не реализовано",
      {exact:false}).waitFor({state:"visible"});
    await page.locator("#bulk-import-form button").filter({hasText:"Подключить выбранные"}).click();
    await page.getByText("Добавлено или уже подключено:",{exact:false})
      .waitFor({state:"visible"});
    assert.equal(bulkCalls,2);
    await page.locator('[data-section="feed"]').click();
    await page.getByText("Проверенный пример").waitFor({state:"visible"});
    await page.locator("#content .tile .tile-actions").first()
      .getByRole("button",{name:"✕ Скрыть"}).click();
    assert.equal(hiddenNews,true);
    await page.locator('[data-section="hidden"]').click();
    await page.getByText("Проверенный пример").waitFor({state:"visible"});
    await page.locator("#content .tile .tile-actions").first()
      .getByRole("button",{name:"↩ Вернуть в ленту"}).click();
    assert.equal(hiddenNews,false);
    await page.locator('[data-section="feed"]').click();
    await page.getByText("Проверенный пример").waitFor({state:"visible"});
    await page.locator("#theme-toggle").click();
    assert.equal(await page.locator("html").getAttribute("data-theme"),"dark");
    await page.locator("#theme-toggle").click();
    assert.equal(await page.locator("html").getAttribute("data-theme"),"light");
    await page.locator("#search").fill("неттакогозаголовка");
    await page.getByText("Ничего не найдено").waitFor({state:"visible"});
    await page.locator("#search").fill("");
    await page.locator("#content .primary-button").first().click();
    await page.getByText("Полный проверенный материал",{exact:false}).waitFor({state:"visible"});
    await page.locator("#reader-note-text").fill("Проверить независимый источник");
    await page.locator("#reader-is-read").check();
    await page.getByRole("button",{name:"Сохранить заметку"}).click();
    await page.getByText("Заметка сохранена.").waitFor({state:"visible"});
    assert.equal(await page.locator("#dialog-overlay").isVisible(),true);
    await page.locator("#dialog-close").click();
    assert.equal(await page.locator("#dialog-overlay").isVisible(),false);
    await page.locator('[data-section="notebook"]').click();
    await page.getByText("Проверить независимый источник").waitFor({state:"visible"});
    await page.locator('[data-section="briefing"]').click();
    await page.getByText("Картина наблюдения").waitFor({state:"visible"});
    await page.locator('[data-section="media"]').click();
    await page.locator("#youtube-url").fill("https://www.youtube.com/watch?v=ABCDEFGHIjk");
    await page.locator("#youtube-form .primary-button").click();
    await page.getByText("AI-провайдер для выжимок не настроен",{exact:false}).waitFor({state:"visible"});
    await page.locator('[data-section="studio"]').click();
    await page.locator("#studio-prompt").fill("Орбиты и глобальные технологии");
    await page.locator("#studio-generate").click();
    assert.equal(await page.locator("#studio-preview svg").count(),1);
    assert.equal(await page.locator("#studio-download").isVisible(),true);
    await page.locator('[data-section="feed"]').click();
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
