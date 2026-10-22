"use strict";
const $ = selector => document.querySelector(selector);
const ICON = name => {
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("aria-hidden","true");
  const use=document.createElementNS("http://www.w3.org/2000/svg","use");
  use.setAttribute("href","#i-"+name);
  svg.append(use);
  return svg;
};
const el=(tag,cls,value)=>{
  const node=document.createElement(tag);
  if(cls)node.className=cls;
  if(value!==undefined)node.textContent=String(value);
  return node;
};
const state={data:null,csrf:"",section:"overview",query:"",videoJob:null,capabilities:null,aiModels:null,aiCatalog:null,accountStatus:null,sourceGroup:"all",sourceTopic:"all"};
const tg=window.Telegram&&window.Telegram.WebApp;
const labels={
  overview:["Информационный обзор","Новости, события, источники и аналитика — всё в одном месте."],
  feed:["Моя лента","Проверенные материалы, подробности и первоисточники."],
  radar:["Радар событий","Публикации на этапе сбора и проверки фактов."],
  interests:["Мои интересы","Настрой, что ОСВЕД должен показывать чаще и реже. Все рекомендации объяснимы."],
  briefing:["Русская сводка","Краткая картина событий на русском языке с подтверждённым статусом каждого материала."],
  notebook:["Мои заметки","Личный исследовательский архив: комментарии и прочитанные материалы."],
  saved:["Избранное","Сохранённые материалы из кабинета и Telegram."],
  hidden:["Скрытые","Убранные из ленты карточки. Можно восстановить без изменения интересов."],
  sources:["Источники","Твой реестр наблюдения и включённые каналы."],
  media:["Медиалаб","Видео YouTube, расшифровки и смысловые выжимки."],
  studio:["Студия иллюстраций","Генеративные SVG-обложки. AI-рендер потребует подключения модели."],
  settings:["Настройки","Статус платформы, оформление и доступные функции."],
};
const errors={
  github_oauth_unconfigured:"GitHub OAuth ещё не настроен на сервере.",
  github_oauth_failed:"GitHub не подтвердил подключение. Повтори попытку.",
  invalid_model_scope:"Укажи корректный идентификатор источника, сценария или профиля.",
  codexsale_unconfigured:"Codex Sale не подключён к веб-контейнеру. Проверь серверные переменные.",
  codexsale_catalog_unavailable:"Не удалось получить каталог моделей Codex Sale.",
  invalid_model_selection:"Модель или назначение не прошли проверку.",
  ai_provider_unconfigured:"AI-провайдер для выжимок не настроен. Нельзя сгенерировать достоверный пересказ без модели.",
  transcription_provider_unconfigured:"Провайдер субтитров не подключён.",
  video_budget_guard_disabled:"Создание новых выжимок закрыто до включения лимита расходов в настройках сервера.",
  video_generation_disabled:"Функция генерации видео отключена в конфигурации.",
  budget_blocked:"Достигнут лимит расходов. Сохранённые выжимки остаются доступными.",
  video_busy:"Уже обрабатывается один ролик — дождись результата.",
  invalid_youtube_link:"Вставь полную ссылку на видео YouTube, shorts или youtu.be.",
  uncertain:"Результат платного запроса не подтверждён. Повтор отключён, чтобы избежать двойных списаний.",
  insufficient_context:"Для качественной выжимки недостаточно контекста.",
  provider_blocked:"Поставщик субтитров заблокировал запрос.",
  youtube_direct_channel_required:"Для бесплатного подключения нужна ссылка YouTube формата /channel/UC….",
  youtube_resolution_consent_required:"Чтобы добавить @ник, разреши одно платное распознавание канала.",
  youtube_resolver_unconfigured:"Для @ника пока не настроен Monid. Ссылка /channel/UC… добавляется бесплатно.",
  invalid_youtube_channel:"Это не ссылка на публичный YouTube-канал.",
  youtube_channel_unavailable:"Не удалось проверить публичную ленту канала.",
  unavailable:"Субтитры этого ролика недоступны.",
  disabled:"Провайдер для генерации не подключён.",
  processing:"Обработка уже идёт.",
};
function friendly(error){
  if(error&&error.payload&&error.payload.error)return errors[error.payload.error]||("Запрос не выполнен: "+error.payload.error);
  return "Не удалось выполнить запрос. Проверь подключение и попробуй снова.";
}
async function api(path,options={}){
  const response=await fetch(path,{
    credentials:"same-origin", ...options,
    headers:{...(options.body?{"Content-Type":"application/json","X-CSRF-Token":state.csrf}:{}),...(options.headers||{})}
  });
  let payload=null;
  try{payload=await response.json();}catch(_){}
  if(!response.ok){const err=new Error("HTTP "+response.status);err.status=response.status;err.payload=payload;throw err;}
  return payload;
}
function theme(mode){
  const next=mode==="light"?"light":"dark";
  document.documentElement.dataset.theme=next;
  document.querySelector('meta[name="theme-color"]').content=next==="light"?"#f3f6fb":"#111a29";
  document.querySelectorAll("[data-theme-toggle]").forEach(button=>{
    button.replaceChildren(ICON(next==="light"?"moon":"sun"));
    button.title=next==="light"?"Включить тёмную тему":"Включить светлую тему";
  });
  try{localStorage.setItem("osved.theme.v1",next);}catch(_){}
}
let remembered="light";
try{remembered=localStorage.getItem("osved.theme.v1")||"light";}catch(_){}
theme(remembered);
document.querySelectorAll("[data-theme-toggle]").forEach(btn=>btn.addEventListener("click",()=>{
  theme(document.documentElement.dataset.theme==="dark"?"light":"dark");
}));
function showAuth(message){
  $("#auth").hidden=false;$("#shell").hidden=true;
  $("#login-state").textContent=message;
}
function showShell(){$("#auth").hidden=true;$("#shell").hidden=false;}
function metric(label,value,note){
  const node=el("div","metric");
  node.append(el("label","",label),el("strong","",value),el("small","",note));
  return node;
}
function empty(title,detail){
  const node=el("article","empty");
  node.append(el("h2","",title),el("p","",detail));
  return node;
}
function pill(title,cls){return el("span",cls||"tag",title);}
function action(text,icon,handler,variant="action"){
  const button=el("button",variant);
  button.type="button";
  if(icon)button.append(ICON(icon));
  button.append(el("span","",text));
  if(handler)button.addEventListener("click",handler);
  return button;
}
function external(url,title){
  if(typeof url!=="string"||!/^https?:\/\//i.test(url))return null;
  try{
    const parsed=new URL(url);
    if(!["http:","https:"].includes(parsed.protocol))return null;
    const a=el("a","secondary",title);
    a.href=parsed.href;a.target="_blank";a.rel="noopener noreferrer";
    a.prepend(ICON("external"));
    return a;
  }catch(_){return null;}
}
const sourceName=x=>x.source_name||x.source||"Первоисточник";
function readingState(kind,id){
  const rows=Array.isArray(state.data?.reading)?state.data.reading:[];
  return rows.find(row=>row.kind===kind&&row.id===id)||
    {kind,id,note:"",is_read:false,updated_at:null};
}
function storeReading(entry){
  if(!Array.isArray(state.data?.reading))state.data.reading=[];
  const rows=state.data.reading;
  const index=rows.findIndex(row=>row.kind===entry.kind&&row.id===entry.id);
  if(index<0)rows.push(entry);else rows[index]=entry;
}
function containsCyrillic(text){
  return /[А-Яа-яЁё]/.test(String(text||""));
}
function readingPanel(item,kind){
  const panel=el("section","reader-note-panel");
  panel.append(el("h3","","Исследовательские заметки"));
  panel.append(el("p","caption","Заметка сохраняется в личной базе ОСВЕД, доступной только владельцу."));
  const form=el("form","reader-note-form");
  const area=el("textarea");area.id="reader-note-text";area.maxLength=4000;
  area.placeholder="Главная мысль, вопросы, что проверить позже…";
  const row=el("label","reader-check");
  const checkbox=el("input");checkbox.type="checkbox";checkbox.id="reader-is-read";
  row.append(checkbox,el("span","","Материал прочитан"));
  const status=el("p","caption");status.setAttribute("role","status");
  const button=el("button","primary-button","Сохранить заметку");button.type="submit";
  form.append(area,row,button,status);panel.append(form);
  const previous=readingState(kind,item.id);
  area.value=previous.note||"";checkbox.checked=Boolean(previous.is_read);
  form.addEventListener("submit",async event=>{
    event.preventDefault();button.disabled=true;status.textContent="Сохраняю…";
    try{
      const result=await api("/api/reader/"+kind+"/"+item.id,{
        method:"POST",body:JSON.stringify({note:area.value,is_read:checkbox.checked})
      });
      storeReading(result);status.textContent="Заметка сохранена.";
    }catch(error){status.textContent=friendly(error);}
    finally{button.disabled=false;}
  });
  return panel;
}
function isHidden(kind,id){
  return (state.data?.hidden||[]).some(x=>x.kind===kind&&x.id===id);
}
function card(item,kind){
  const type=kind==="radar"?"radar":item.kind||"news";
  const node=el("article","tile");
  const head=el("div","kicker");
  head.append(el("span","",type==="radar"?"СИГНАЛ ИСТОЧНИКА":type==="video"?"МЕДИАЛАБ":"РЕДАКЦИОННЫЙ МАТЕРИАЛ"));
  if(type==="radar")head.append(pill("НЕ ПРОВЕРЕНО","unverified"));
  if(item.language==="original")head.append(pill("ИНОСТРАННЫЙ ОРИГИНАЛ","tag off"));
  const note=readingState(type,item.id);
  if(note.is_read)head.append(pill("ПРОЧИТАНО","tag"));
  node.append(head,el("h2","",item.title||"Без заголовка"));
  if(item.summary||item.source||item.source_name){
    node.append(el("p","",item.summary||sourceName(item)));
  }
  node.append(el("span","tile-meta",sourceName(item)));
  if(item.recommendation){
    const detail=el("p","recommendation-reason","Почему показано: "+item.recommendation.reason);
    node.append(detail);
  }
  const actions=el("div","tile-actions");
  actions.append(action("Читать", "news", ()=>openArticle(item,type),"primary-button"));
  const link=external(item.url,"Первоисточник");
  if(link)actions.append(link);
  if(type!=="radar"){
    const save=action(item.saved?"★ Сохранено":"☆ Сохранить","star",async()=>{
      save.disabled=true;
      try{
        const next=!item.saved;
        await api("/api/bookmark",{method:"POST",body:JSON.stringify({kind:item.kind,id:item.id,saved:next})});
        item.saved=next;
        save.lastElementChild.textContent=next?"★ Сохранено":"☆ Сохранить";
      }catch(_){save.lastElementChild.textContent="Не удалось сохранить";}
      finally{save.disabled=false;}
    },"secondary-button");
    actions.append(save);
  }
  const hidden=isHidden(type,item.id);
  actions.append(action(hidden?"↩ Вернуть в ленту":"✕ Скрыть","close",async()=>{
    const button=actions.lastElementChild;
    button.disabled=true;
    try{
      await api("/api/hidden",{
        method:"POST",body:JSON.stringify({kind:type,id:item.id,hidden:!hidden})
      });
      if(!Array.isArray(state.data.hidden))state.data.hidden=[];
      state.data.hidden=state.data.hidden.filter(x=>!(x.kind===type&&x.id===item.id));
      if(!hidden)state.data.hidden.push({kind:type,id:item.id});
      render();
    }catch(error){
      button.disabled=false;
      button.lastElementChild.textContent=friendly(error);
    }
  },"secondary-button"));
  node.append(actions);
  const reactions=el("details","reaction-details");
  const preview=el("summary","","🎯 Настроить рекомендации");
  reactions.append(preview);
  const buttons=el("div","reaction-buttons");
  const current=item.recommendation?.action||null;
  const options=[
    ["more","👍 Больше такого"],["less","👎 Меньше такого"],
    ["not_interested","🚫 Не моё"],["already_known","✓ Уже знаю"],
    ["deeper","📚 Нужен глубокий разбор"],["follow","🔔 Следить за темой"],
    ["clear","↺ Сбросить оценку"],
  ];
  for(const [reaction,label] of options){
    const button=action((reaction===current?"● ":"")+label,null,async()=>{
      button.disabled=true;
      try{
        await api("/api/personalization/feedback",{
          method:"POST",body:JSON.stringify({kind:type,id:item.id,action:reaction})
        });
        await loadDashboard();
      }catch(error){
        const info=el("span","reaction-error",friendly(error));
        buttons.append(info);button.disabled=false;
      }
    },"secondary-button");
    if(reaction===current)button.classList.add("chosen");
    buttons.append(button);
  }
  reactions.append(buttons);
  node.append(reactions);
  return node;
}
function heading(section){
  const title=labels[section]||labels.overview;
  $("#page-title").textContent=title[0];
  $("#page-description").textContent=title[1];
  $("#crumb").textContent=title[0].toUpperCase();
  document.querySelectorAll(".nav-link").forEach(b=>{
    b.classList.toggle("selected",b.dataset.section===section);
    if(b.dataset.section===section)b.setAttribute("aria-current","page");
    else b.removeAttribute("aria-current");
  });
}
function matches(item){
  if(!state.query)return true;
  return [item.title,item.summary,item.source,item.source_name,item.kind]
    .some(value=>String(value||"").toLowerCase().includes(state.query));
}
function filter(items){return items.filter(matches);}
async function changePriority(topic,delta){
  const next=Math.max(-3,Math.min(3,topic.priority+delta));
  try{
    await api("/api/personalization/topic",{
      method:"POST",body:JSON.stringify({topic:topic.id,priority:next})
    });
    await loadDashboard();
  }catch(error){
    const message=el("div","reaction-error",friendly(error));
    $("#section-tools").append(message);
  }
}
function parseSourceLine(raw){
  let line=String(raw||"").replace(/^\uFEFF/,"").trim();
  if(!line||line.startsWith("#")||/^(url|link|ссылка)$/i.test(line))return null;
  if(line.startsWith('"')){
    const m=line.match(/^"([^"]+)"(?:[,;].*)?$/);
    if(m)line=m[1];
  }else line=line.split(/[,;]/,1)[0].trim();
  line=line.trim();
  if(line.length>400)return {raw,reason:"Слишком длинная ссылка"};
  if(/^r\/[a-z0-9_]{2,21}$/i.test(line))
    return {raw,kind:"reddit",locator:line};
  if(/^[a-z0-9-]+\/[a-z0-9_.-]+$/i.test(line)&&!line.startsWith("r/"))
    return {raw,kind:"github",locator:line};
  let url;
  try{url=new URL(line);}catch(_){return {raw,reason:"Неизвестный формат"};}
  if(url.protocol!=="https:"||url.username||url.password||url.port||url.hash||url.search)
    return {raw,reason:"Нужна обычная публичная HTTPS-ссылка без параметров"};
  const host=url.hostname.toLowerCase();
  const path=url.pathname.replace(/^\/|\/$/g,"");
  if(["github.com","www.github.com"].includes(host)){
    if(/^[a-z0-9-]+\/[a-z0-9_.-]+$/i.test(path)&&!path.includes(".."))
      return {raw,kind:"github",locator:line};
    return {raw,reason:"Нужна ссылка на корень репозитория"};
  }
  if(["reddit.com","www.reddit.com"].includes(host)){
    if(/^r\/[a-z0-9_]{2,21}$/i.test(path))
      return {raw,kind:"reddit",locator:line};
    return {raw,reason:"Нужна ссылка на сообщество r/…"};
  }
  if(["youtube.com","www.youtube.com","m.youtube.com"].includes(host)){
    if(/^channel\/UC[a-z0-9_-]{22}$/i.test(path))
      return {raw,kind:"youtube",locator:line};
    return {raw,reason:"Для пакета YouTube пока нужен адрес /channel/UC…"};
  }
  return {raw,reason:"Подключение этой площадки ещё не реализовано"};
}
function sourceImportPanel(){
  const panel=el("section","panel source-add-panel batch-panel");
  panel.append(el("h2","","Импорт списка ссылок"));
  panel.append(el("p","","Один канал, репозиторий или сообщество на строку. TXT или CSV (первый столбец — ссылка). До 25 ссылок за пакет. Перед добавлением покажем, какие ссылки поддерживаются; вход в личные аккаунты здесь не требуется."));
  const form=el("form");form.id="bulk-import-form";
  const fileLabel=el("label","","Загрузить файл TXT / CSV");
  const file=el("input");file.id="bulk-import-file";file.type="file";file.accept=".txt,.csv,text/plain,text/csv";
  fileLabel.append(file);
  const textLabel=el("label","","Или вставить ссылки списком");textLabel.htmlFor="bulk-import-text";
  const area=el("textarea");area.id="bulk-import-text";area.rows=5;area.maxLength=65536;
  area.placeholder="https://github.com/microsoft/vscode\nr/Python\nhttps://www.youtube.com/channel/UC…";
  const topicLabel=el("label","","Категория по умолчанию");topicLabel.htmlFor="bulk-import-topic";
  const topic=el("select","source-filter");topic.id="bulk-import-topic";
  const unassigned=el("option","","Без категории");unassigned.value="";topic.append(unassigned);
  for(const entry of (state.data?.personalization?.topics||[])){
    const opt=el("option","",entry.title);opt.value=entry.id;topic.append(opt);
  }
  const preview=el("button","secondary-button","Предпросмотр");preview.type="button";
  const commit=el("button","primary-button","Подключить выбранные");commit.type="button";commit.disabled=true;
  const message=el("p","source-add-status");message.id="bulk-import-status";message.setAttribute("role","status");
  const results=el("div","batch-preview");results.id="bulk-import-preview";
  let parsed=[];
  file.addEventListener("change",async()=>{
    if(!file.files?.length)return;
    const selected=file.files[0];
    if(selected.size>65536||!/.\.(txt|csv)$/i.test(selected.name)){
      message.textContent="Поддерживается TXT/CSV до 64 КБ.";
      return;
    }
    area.value=await selected.text();
    message.textContent="Файл загружен локально. Нажми «Предпросмотр».";
  });
  preview.addEventListener("click",()=>{
    parsed=[];results.replaceChildren();commit.disabled=true;
    const rows=area.value.split(/\r?\n/).map(parseSourceLine).filter(Boolean);
    if(rows.length>25){message.textContent="В одном пакете не больше 25 строк. Раздели файл.";return;}
    const used=new Set();
    for(const row of rows){
      const key=(row.kind||"")+":"+(row.locator||"").toLowerCase();
      if(row.kind&&used.has(key))continue;
      if(row.kind)used.add(key);
      parsed.push(row);
      const label=el("label","batch-row");
      const checkbox=el("input");checkbox.type="checkbox";checkbox.checked=Boolean(row.kind);
      checkbox.disabled=!row.kind;row.checkbox=checkbox;
      const detail=el("span","",row.raw+" · "+(row.kind||row.reason));
      label.append(checkbox,detail);results.append(label);
    }
    const total=parsed.filter(x=>x.kind).length;
    message.textContent="Распознано: "+total+" · Неподдерживаемых: "+(parsed.length-total)+". Можно снять галочки перед импортом.";
    commit.disabled=!total;
  });
  commit.addEventListener("click",async()=>{
    const selected=parsed.filter(x=>x.kind&&x.checkbox.checked);
    if(!selected.length){message.textContent="Выбери хотя бы одну ссылку.";return;}
    commit.disabled=true;preview.disabled=true;
    let ok=0;const errors=[];
    for(const item of selected){
      message.textContent="Подключаю "+(ok+errors.length+1)+" из "+selected.length+"…";
      try{
        if(item.kind==="youtube"){
          await api("/api/youtube/channels/add",{
            method:"POST",body:JSON.stringify({url:item.locator})
          });
        }else{
          await api("/api/public-sources/add",{
            method:"POST",body:JSON.stringify({
              kind:item.kind,locator:item.locator,topic:topic.value,
            })
          });
        }
        ok++;
      }catch(e){errors.push(item.raw+": "+friendly(e));}
    }
    try{
      state.data=await api("/api/overview");render();
      const status=$("#bulk-import-status");
      if(status)status.textContent="Добавлено или уже подключено: "+ok+
        " · Ошибок: "+errors.length+(errors.length?" · "+errors.slice(0,2).join(" | "):"");
    }catch(e){message.textContent="Изменения сохранены, но обновление списка не удалось: "+friendly(e);}
  });
  form.append(fileLabel,textLabel,area,topicLabel,topic,preview,commit,message,results);
  panel.append(form);
  return panel;
}
function render(){
  if(!state.data)return;
  const {feed,radar,sources,health}=state.data;
  const all=Array.isArray(feed)?feed:[];
  const signals=Array.isArray(radar)?radar:[];
  const streams=Array.isArray(sources)?sources:[];
  const visibleAll=all.filter(x=>!isHidden(x.kind,x.id));
  const visibleSignals=signals.filter(x=>!isHidden("radar",x.id));
  const hiddenItems=[
    ...all.filter(x=>isHidden(x.kind,x.id)),
    ...signals.filter(x=>isHidden("radar",x.id)),
  ];
  const news=visibleAll.filter(x=>x.kind==="news");
  const video=visibleAll.filter(x=>x.kind==="video");
  const saved=all.filter(x=>x.saved);
  const root=$("#content"),stats=$("#metrics");
  root.replaceChildren();stats.replaceChildren();$("#section-tools").replaceChildren();
  heading(state.section);
  stats.append(
    metric("Проверенные материалы",news.length,"Фактчекинг завершён"),
    metric("Сигналы радара",signals.length,"Ожидают проверки"),
    metric("Активные источники",streams.filter(x=>x.enabled).length,"Под наблюдением"),
    metric("Отправлено за сутки",Number(health.news_24h)||0,"Новостная доставка")
  );
  const add=(array,kind)=>filter(array).forEach(x=>root.append(card(x,kind)));
  const note=(title,message)=>root.append(empty(title,message));
  const section=state.section;
  $("#result-count").textContent=String(
    section==="feed"?news.length:section==="radar"?visibleSignals.length:section==="hidden"?hiddenItems.length:section==="saved"?saved.length:section==="sources"?streams.length:section==="notebook"?(state.data.reading||[]).filter(x=>x.note||x.is_read).length:news.length+signals.length
  )+" материалов / объектов";
  if(section==="overview"){
    if(!news.length)note("Информационная картина","Проверенные публикации ещё не готовы. Ниже доступны сигналы из реальных источников. Это не готовые новости.");
    add(news.slice(0,5),"feed");
    add(video.slice(0,3),"feed");
    if(visibleSignals.length){
      root.append(el("div","statusline","СИГНАЛЫ ИСТОЧНИКОВ · НЕПРОВЕРЕННЫЕ"));
      add(visibleSignals.slice(0,9),"radar");
    }
  }else if(section==="feed"){
    if(!news.length){
      note("Проверенных карточек пока нет","Лента формируется после проверки доказательств. Ниже реальные сообщения из источников, которые ещё не прошли проверку.");
      if(visibleSignals.length){
        root.append(el("div","statusline","СИГНАЛЫ ИСТОЧНИКОВ · НЕПРОВЕРЕННЫЕ"));
        add(visibleSignals.slice(0,12),"radar");
      }
    }else add(news,"feed");
  }else if(section==="radar"){
    if(!visibleSignals.length)note("Радар пока пуст","Новые сигналы появятся после следующего сбора источников.");
    else add(visibleSignals,"radar");
  }else if(section==="briefing"){
    const russianNews=filter(news.filter(x=>x.language!=="original"));
    const russianRadar=filter(visibleSignals.filter(x=>x.language!=="original"));
    const foreign=filter([...news,...visibleSignals].filter(x=>x.language==="original"));
    const panel=el("section","briefing-panel");
    panel.append(el("span","eyebrow","РУССКОЯЗЫЧНЫЙ ОБЗОР / ПРОВЕРЕННЫЕ ДАННЫЕ"));
    panel.append(el("h2","","Картина наблюдения"));
    panel.append(el("p","","Проверенных материалов: "+news.length+
      " · Сигналов в проверке: "+signals.length+
      " · Источников активно: "+streams.filter(x=>x.enabled).length+
      ". Сводка составлена из существующих данных — без выдуманного перевода и AI-выводов."));
    panel.append(el("p","caption","Оригиналы на других языках сохраняются с явной пометкой. Их полноценный перевод станет доступен после настройки модели и контроля качества."));
    $("#section-tools").append(panel);
    root.append(el("div","statusline","ПРОВЕРЕННЫЕ МАТЕРИАЛЫ · РУССКАЯ РЕДАКЦИЯ"));
    if(russianNews.length)add(russianNews,"feed");
    else note("Проверенных русскоязычных статей пока нет","Публикации появятся после прохождения фактчекинга и проверки языка.");
    root.append(el("div","statusline","РУССКОЯЗЫЧНЫЕ СИГНАЛЫ · НЕПРОВЕРЕННЫЕ"));
    if(russianRadar.length)add(russianRadar,"radar");
    else note("Русскоязычных сигналов пока нет","Система не переводит иностранные заголовки по догадке.");
    if(foreign.length){
      root.append(el("div","statusline","ИНОСТРАННЫЕ ОРИГИНАЛЫ · БЕЗ АВТОПЕРЕВОДА"));
      foreign.slice(0,12).forEach(x=>root.append(card(x,x.kind||"radar")));
    }
  }else if(section==="notebook"){
    const notes=(Array.isArray(state.data.reading)?state.data.reading:[])
      .filter(x=>x.note||x.is_read);
    if(!notes.length)note("Исследовательский архив пуст","Открой любой материал, впиши заметку или отметь как прочитанный. Все записи сохраняются на сервере.");
    for(const entry of notes){
      const item=[...news,...video,...signals].find(x=>x.kind===entry.kind&&x.id===entry.id)||
        {kind:entry.kind,id:entry.id,title:"Материал №"+entry.id,summary:"Материал не входит в текущую выборку ленты."};
      if(state.query&&!matches({...item,summary:entry.note}))continue;
      const cardNode=el("article","tile");
      cardNode.append(el("div","kicker",entry.is_read?"ПРОЧИТАНО":"В ЗАМЕТКАХ"));
      cardNode.append(el("h2","",item.title));
      cardNode.append(el("p","",entry.note||"Без заметки — отмечено как прочитанное."));
      cardNode.append(el("span","tile-meta",entry.updated_at||""));
      const actions=el("div","tile-actions");
      actions.append(action("Читать и изменить","note",()=>openArticle(item,entry.kind),"primary-button"));
      cardNode.append(actions);root.append(cardNode);
    }
  }else if(section==="hidden"){
    if(!hiddenItems.length)note("Нет скрытых материалов","Здесь появятся карточки, которые ты закрыл без оценки. Их всегда можно вернуть.");
    for(const item of hiddenItems)add([item],item.kind==="radar"?"radar":"feed");
  }else if(section==="saved"){
    if(!saved.length)note("Сохранений пока нет","В ленте нажми «Сохранить» на нужном материале.");
    else add(saved,"feed");
  }else if(section==="interests"){
    const data=state.data.personalization||{};
    const topics=Array.isArray(data.topics)?data.topics:[];
    const intro=el("div","panel");
    intro.append(el("h2","","Управление информационным потоком"));
    intro.append(el("p","","От -3 (реже) до +3 (чаще). Реакции на статьи и сигналы дополнительно корректируют порядок. Это прозрачный локальный алгоритм, пока без AI-предсказаний."));
    intro.append(el("p","caption","Текущее количество оценок: "+(data.feedback_count||0)+". Приоритет меняет порядок, но не удаляет источники и не превращает сигналы в проверенные новости."));
    $("#section-tools").append(intro);
    for(const topic of topics){
      const tile=el("article","tile topic-tile");
      tile.append(el("div","kicker","ПЕРСОНАЛЬНАЯ ТЕМА"));
      tile.append(el("h2","",topic.title));
      const row=el("div","priority-row");
      const minus=action("−",null,()=>changePriority(topic,-1),"secondary-button");
      minus.disabled=topic.priority<=-3;
      const value=el("strong","priority-value",topic.priority>0?"+"+topic.priority:topic.priority);
      const plus=action("+",null,()=>changePriority(topic,1),"secondary-button");
      plus.disabled=topic.priority>=3;
      row.append(minus,value,plus);
      tile.append(row);
      tile.append(el("p","",topic.priority>0?"Показывать больше материалов этой темы":topic.priority<0?"Показывать меньше материалов этой темы":"Нейтральный приоритет"));
      root.append(tile);
    }
    const tools=el("div","panel personalization-reset");
    tools.append(el("h2","","Управление персонализацией"));
    tools.append(el("p","","Можно сбросить все сохранённые реакции и ручные приоритеты. Избранное и исследовательские заметки сохранятся."));
    const reset=action("Сбросить мои предпочтения","refresh",async()=>{
      if(!window.confirm("Сбросить реакции и приоритеты тем? Избранное и заметки останутся."))return;
      reset.disabled=true;
      try{
        await api("/api/personalization/reset",{method:"POST",body:JSON.stringify({confirm:true})});
        await loadDashboard();
      }catch(error){tools.append(el("p","reaction-error",friendly(error)));reset.disabled=false;}
    },"secondary-button");
    tools.append(reset);$("#section-tools").append(tools);
  }else if(section==="sources"){
    const header=el("div","panel source-catalog-head");
    header.append(el("h2","","Каталог источников"));
    header.append(el("p","","Платформы → авторы и каналы → темы. Это реально настроенные источники ОСВЕД, а не список всех ваших подписок в приложениях."));
    const platformControl=el("select","source-filter");platformControl.id="source-platform";
    platformControl.setAttribute("aria-label","Тип платформы");
    const topicControl=el("select","source-filter");topicControl.id="source-topic";
    topicControl.setAttribute("aria-label","Тема");
    function option(value,label,selected){
      const node=el("option","",label);node.value=value;node.selected=value===selected;return node;
    }
    const groups=[...new Set(streams.map(s=>s.category||"Другие платформы"))].sort((a,b)=>a.localeCompare(b,"ru"));
    platformControl.append(option("all","Все платформы",state.sourceGroup));
    groups.forEach(group=>platformControl.append(option(group,group,state.sourceGroup)));
    const topics=[...new Set(streams.flatMap(s=>Array.isArray(s.topics)?s.topics:[]))].sort((a,b)=>a.localeCompare(b,"ru"));
    topicControl.append(option("all","Все темы",state.sourceTopic));
    topics.forEach(topic=>topicControl.append(option(topic,topic,state.sourceTopic)));
    platformControl.addEventListener("change",()=>{state.sourceGroup=platformControl.value;render();});
    topicControl.addEventListener("change",()=>{state.sourceTopic=topicControl.value;render();});
    const controls=el("div","catalog-filters");controls.append(platformControl,topicControl);
    header.append(controls);
    const meta=el("p","caption","Подключено к реестру: "+streams.length+
      " · Включено: "+streams.filter(s=>s.enabled).length+
      " · Ошибки: "+streams.filter(s=>s.status==="error").length);
    header.append(meta);
    const access=el("div","connection-guide");
    access.append(el("strong","","Личные подписки из аккаунтов"));
    access.append(el("p","","TXT/CSV и список публичных ссылок можно загрузить ниже. Личные подписки из подключённых аккаунтов — отдельный этап OAuth с правом отзыва доступа. Пароли и браузерные сессии не требуются."));
    header.append(access);
    $("#section-tools").append(header);
    const addPanel=el("section","panel source-add-panel");
    addPanel.append(el("h2","","Добавить собственный источник"));
    addPanel.append(el("p","","Подключи публичный YouTube-канал бесплатно по его прямой ссылке. ОСВЕД сохранит подписку в общей базе сайта и Telegram. Новые ролики поступают в радар при работе расписания сборщика."));
    const addForm=el("form");addForm.id="youtube-add-form";
    const label=el("label","","YouTube: @ник или обычная ссылка на канал");label.htmlFor="youtube-channel-url";
    const input=el("input");input.type="text";input.id="youtube-channel-url";input.required=true;
    input.autocomplete="off";input.placeholder="@канал или https://youtube.com/channel/UC…";
    input.maxLength=2048;
    const resolveLabel=el("label","reader-check");
    const resolveInput=el("input");resolveInput.type="checkbox";resolveInput.id="youtube-resolve-consent";
    resolveLabel.append(resolveInput,el("span","",
      "Разрешаю один запрос Monid для определения @ника (оценка $0.0015). Для прямой /channel/UC… ссылки он не нужен."));
    const submit=el("button","primary-button","Добавить канал");submit.type="submit";
    const addStatus=el("p","source-add-status");addStatus.setAttribute("role","status");
    addForm.append(label,input,resolveLabel,submit,addStatus);
    addForm.addEventListener("submit",async event=>{
      event.preventDefault();submit.disabled=true;addStatus.textContent="Проверяю публичную ленту…";
      try{
        const outcome=await api("/api/youtube/channels/add",{
          method:"POST",body:JSON.stringify({url:input.value.trim(),allow_paid_resolution:resolveInput.checked})
        });
        addStatus.textContent=outcome.existing?
          "Канал уже подключён: "+outcome.title:
          "Канал добавлен: "+outcome.title;
        input.value="";
        const fresh=await api("/api/overview");state.data=fresh;
        render();
        const status=$("#youtube-add-form .source-add-status");
        if(status)status.textContent=outcome.existing?
          "Канал уже был в реестре.":"Готово! Канал сохранён и появится в реестре.";
      }catch(error){
        addStatus.textContent=friendly(error);
        if(error.payload?.detail)addStatus.textContent+=" "+error.payload.detail;
        submit.disabled=false;
      }
    });
    addPanel.append(addForm);
    const hint=el("p","caption source-account-help",
      "Личный аккаунт X, Reddit или YouTube пока нельзя авторизовать здесь. Для чтения ваших подписок нужен официальный OAuth, отдельное согласие и возможность отозвать доступ. Это следующий этап, а не работающая кнопка.");
    addPanel.append(hint);
    $("#section-tools").append(addPanel);
    const publicPanel=el("section","panel source-add-panel");
    publicPanel.append(el("h2","","Добавить GitHub или Reddit"));
    publicPanel.append(el("p","","Добавь публичный репозиторий или сообщество в радар ОСВЕД. Подписка сразу сохраняется, а новые публикации появятся после успешного сбора. Личный аккаунт и API-ключ не нужны."));
    const publicForm=el("form");publicForm.id="public-source-add-form";
    const kindLabel=el("label","","Платформа");kindLabel.htmlFor="public-source-kind";
    const kindSelect=el("select","source-filter");kindSelect.id="public-source-kind";
    for(const [value,title] of [["github","GitHub · релизы"],["reddit","Reddit · сообщество"]]){
      const opt=el("option","",title);opt.value=value;kindSelect.append(opt);
    }
    const urlLabel=el("label","","Репозиторий или сообщество");urlLabel.htmlFor="public-source-locator";
    const urlInput=el("input");urlInput.id="public-source-locator";urlInput.required=true;urlInput.maxLength=300;
    urlInput.placeholder="owner/repository";
    kindSelect.addEventListener("change",()=>{
      urlInput.placeholder=kindSelect.value==="github"?"owner/repository":"r/Python";
    });
    const topicLabel=el("label","","Тема в ОСВЕД");topicLabel.htmlFor="public-source-topic";
    const topicSelect=el("select","source-filter");topicSelect.id="public-source-topic";
    const fallback=el("option","","Без категории");fallback.value="";topicSelect.append(fallback);
    for(const topic of (state.data.personalization?.topics||[])){
      const opt=el("option","",topic.title);opt.value=topic.id;topicSelect.append(opt);
    }
    const addButton=el("button","primary-button","Подключить публичный источник");
    addButton.type="submit";
    const publicStatus=el("p","source-add-status");publicStatus.setAttribute("role","status");
    publicForm.append(kindLabel,kindSelect,urlLabel,urlInput,topicLabel,topicSelect,addButton,publicStatus);
    publicForm.addEventListener("submit",async event=>{
      event.preventDefault();addButton.disabled=true;publicStatus.textContent="Сохраняю источник…";
      try{
        const added=await api("/api/public-sources/add",{
          method:"POST",body:JSON.stringify({
            kind:kindSelect.value,locator:urlInput.value.trim(),topic:topicSelect.value
          })
        });
        state.data=await api("/api/overview");render();
        const status=$("#public-source-add-form .source-add-status");
        if(status)status.textContent=added.existing?
          "Источник уже подключён.":"Источник добавлен. Сбор начнётся по расписанию.";
      }catch(error){
        publicStatus.textContent=friendly(error)+
          (error.payload?.detail?" "+error.payload.detail:"");
        addButton.disabled=false;
      }
    });
    publicPanel.append(publicForm);
    publicPanel.append(el("p","caption source-account-help",
      "GitHub читает только публичные релизы; Reddit — открытые сообщения сообщества. Чтобы импортировать личные подписки из X/Reddit/YouTube, понадобится отдельный официальный OAuth."));
    $("#section-tools").append(publicPanel);
    $("#section-tools").append(sourceImportPanel());
    const chosen=filter(streams).filter(s=>
      (state.sourceGroup==="all"||s.category===state.sourceGroup)&&
      (state.sourceTopic==="all"||(Array.isArray(s.topics)&&s.topics.includes(state.sourceTopic)))
    );
    $("#result-count").textContent=chosen.length+" из "+streams.length+" источников";
    if(!chosen.length)note("Нет источников с такими фильтрами","Выбери другую платформу или тему. Новые подключения появятся после настройки коннектора.");
    for(const group of groups){
      const subset=chosen.filter(s=>(s.category||"Другие платформы")===group);
      if(!subset.length)continue;
      root.append(el("h2","source-category-title",group+" · "+subset.length));
      for(const source of subset){
        const tile=el("article","tile source-tile");
        tile.append(el("div","kicker",source.platform||source.kind||"Источник"));
        tile.append(el("h2","",source.name||source.id));
        const tags=el("div","source-tags");
        tags.append(pill(source.enabled?"ВКЛЮЧЁН":"ПАУЗА",source.enabled?"tag":"tag off"));
        if(source.status==="error")tags.append(pill("ОШИБКА СБОРА","tag off"));
        if(source.status==="ready"&&source.enabled)tags.append(pill("НЕТ ЗАРЕГИСТРИРОВАННОЙ ОШИБКИ","tag"));
        for(const topic of (source.topics||[]).slice(0,7))tags.append(pill(topic,"tag"));
        if(!source.topics?.length)tags.append(pill("ТЕМА НЕ ЗАДАНА","tag off"));
        tile.append(tags);
        tile.append(el("p","",source.platform_description||"Публичный источник"));
        tile.append(el("span","tile-meta",source.last_success_at?
          "Последний успешный сбор: "+source.last_success_at:"Успешный сбор пока не подтверждён"));
        const actions=el("div","tile-actions");
        const link=external(source.url,"Открыть источник");if(link)actions.append(link);
        const button=action(source.enabled?"Приостановить":"Включить","settings",async()=>{
          button.disabled=true;
          try{
            const result=await api("/api/source",{
              method:"POST",body:JSON.stringify({id:source.id,enabled:!source.enabled})
            });
            source.enabled=result.enabled;render();
          }catch(error){button.lastElementChild.textContent=friendly(error);button.disabled=false;}
        });
        actions.append(button);
        if(source.kind==="youtube"&&source.id.startsWith("youtube_user_")){
          const remove=action("Удалить канал","close",async()=>{
            if(!window.confirm("Удалить отслеживание канала? Уже сохранённые материалы останутся."))return;
            remove.disabled=true;
            try{
              await api("/api/youtube/channels/remove",{
                method:"POST",body:JSON.stringify({id:source.id})
              });
              state.data=await api("/api/overview");render();
            }catch(error){remove.lastElementChild.textContent=friendly(error);remove.disabled=false;}
          },"secondary-button source-remove");
          actions.append(remove);
        }
        if((source.kind==="github"||source.kind==="reddit")
            &&source.id.startsWith("user_"+source.kind+"_")){
          const removePublic=action("Удалить источник","close",async()=>{
            if(!window.confirm("Удалить подписку? История собранных материалов останется."))return;
            removePublic.disabled=true;
            try{
              await api("/api/public-sources/remove",{
                method:"POST",body:JSON.stringify({id:source.id})
              });
              state.data=await api("/api/overview");render();
            }catch(error){
              removePublic.lastElementChild.textContent=friendly(error);
              removePublic.disabled=false;
            }
          },"secondary-button source-remove");
          actions.append(removePublic);
        }
        tile.append(actions);root.append(tile);
      }
    }
  }else if(section==="media"){
    mediaTools();
    if(video.length)add(video,"feed");
    else note("Сохранённые видео пока отсутствуют","Вставь ссылку на видео в форму выше для выжимки. Уже готовые материалы будут доступны в кабинете.");
  }else if(section==="studio"){
    studioTools();
    note("AI-иллюстрации","Абстрактную SVG-обложку можно создать и сохранить прямо сейчас. Нейросетевая генерация фотореалистичных картинок потребует отдельного подключённого и проверенного сервиса.");
  }else if(section==="settings"){
    const panel=el("div","panel");
    panel.append(el("h2","","Возможности ОСВЕД"));
    if(state.capabilities){
      const details=el("div","capability-list");
      const entries=[
        ["Выжимки YouTube",state.capabilities.video?.ready,
          errors[state.capabilities.video?.reason]||"Подключено"],
        ["Перевод статей",state.capabilities.translation?.ready,
          "Нужна отдельная проверенная модель перевода и ограничение затрат"],
        ["Нейросетевые изображения",state.capabilities.image_ai?.ready,
          "Провайдер изображений не подключён; SVG-обложки доступны"],
        ["Личные OAuth-подписки",state.capabilities.accounts?.oauth_ready,
          "Пока только публичные источники"],
      ];
      for(const [name,ready,description] of entries){
        const row=el("div","capability-row");
        row.append(el("strong","",name));
        row.append(pill(ready?"ГОТОВО":"ТРЕБУЕТ ПОДКЛЮЧЕНИЯ",ready?"tag":"tag off"));
        row.append(el("span","",description));
        details.append(row);
      }
      panel.append(details);
    }
    const provider=el("section","connection-guide");
    provider.append(el("strong","","AI-провайдер и выбор моделей"));
    provider.append(el("p","",
      "Основной целевой провайдер — Codex Sale. Ниже показаны сохранённые назначения моделей, но запуск внешней генерации через Codex Sale ещё не подтверждён. Существующий YouTube-пайплайн зависит от OpenRouter и Monid. Ключи API задаются только на сервере."));
    panel.append(provider);
    if(state.aiModels){
      const models=el("section","connection-guide");
      models.append(el("strong","","AI-модели и обработка · действующие назначения"));
      models.append(el("p","","Настройки читаются из общего хранилища сайта и Telegram. Исполнение через Codex Sale пока не подтверждено; выбор модели не означает, что генерация включена."));
      const taskNames={news:"Новости",research:"Исследования",search:"Поиск",video:"Видео"};
      for(const [task,selection] of Object.entries(state.aiModels.selections||{})){
        const row=el("div","capability-row");
        row.append(el("strong","",taskNames[task]||task));
        row.append(el("span","",selection.model+" · "+selection.origin));
        row.append(pill(selection.verified?"ПРОВЕРЕНО":"НЕ ПРОВЕРЕНО",selection.verified?"tag":"tag off"));
        models.append(row);
      }
      const btn=el("button","","Получить доступные модели");
      btn.type="button";
      btn.addEventListener("click",async()=>{
        btn.disabled=true;
        try{
          const catalogue=await api("/api/ai/catalog");
          state.aiCatalog=catalogue.models||[];
          render();
        }catch(error){btn.disabled=false;alert(friendly(error));}
      });
      models.append(btn);
      if(state.aiCatalog){
        const note=el("p","","Модели получены от провайдера. Это не проверка возможности генерации или цены.");
        models.append(note);
        const scopeRow=el("div","capability-row");
        const scopePick=el("select","");
        for(const [value,title] of [["task","Задача (общая)"],["source","Источник"],["scenario","Сценарий"],["profile","Профиль"]]){
          const o=el("option","",title);o.value=value;scopePick.append(o);
        }
        const scopeId=el("input","");scopeId.placeholder="ID источника / сценария / профиля";
        scopeId.maxLength=128;scopeId.disabled=true;
        scopePick.addEventListener("change",()=>{scopeId.disabled=scopePick.value==="task";});
        scopeRow.append(scopePick,scopeId);models.append(scopeRow);
        for(const [task,selection] of Object.entries(state.aiModels.selections||{})){
          const row=el("div","capability-row");
          row.append(el("strong","",taskNames[task]||task));
          const picker=el("select","");
          for(const value of state.aiCatalog){
            const option=el("option","",value);
            option.value=value;
            picker.append(option);
          }
          if(state.aiCatalog.includes(selection.model))picker.value=selection.model;
          else picker.selectedIndex=-1;
          const save=el("button","","Сохранить");
          save.disabled=picker.selectedIndex<0;
          save.addEventListener("click",async()=>{
            save.disabled=true;
            try{
              const scope=scopePick.value==="task"?null:scopePick.value;
              const id=scope?scopeId.value.trim():null;
              if(scope&&!/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/.test(id)){
                throw {payload:{error:"invalid_model_scope"}};
              }
              await api("/api/ai/models",{method:"POST",body:JSON.stringify({
                task,model:picker.value,...(scope?{scope,scope_id:id}:{})
              })});
              state.aiModels=await api("/api/ai/models");
              render();
            }catch(error){save.disabled=false;alert(friendly(error));}
          });
          picker.addEventListener("change",()=>{save.disabled=!picker.value;});
          row.append(picker,save);models.append(row);
        }
      }
      models.append(el("p","","Сохранение выбора не включает платные запросы. Ключи API указываются только на сервере."));
      panel.append(models);
    }
    const accounts=el("section","panel account-status");
    accounts.append(el("h2","","Мои подключённые аккаунты"));
    accounts.append(el("p","","Личный вход в ОСВЕД через Telegram не даёт доступа к подпискам других сервисов. OAuth-авторизация YouTube и GitHub пока не включена: будет доступна после проверки callback, безопасного хранилища токенов и возможности отзыва разрешений."));
    for(const [service,key] of [["YouTube","youtube"],["GitHub","github"]]){
      const row=el("div","capability-row");
      const item=state.accountStatus?.accounts?.[key];
      row.append(el("strong","",service),pill(item?.connected?"ПОДКЛЮЧЁН":"НЕ ПОДКЛЮЧЁН",item?.connected?"tag":"tag off"));
      row.append(el("span","",item?.configuration_present
        ?"OAuth-приложение настроено. Авторизация пока недоступна до завершения защищённого callback."
        :"Требуется настройка OAuth-приложения на сервере."));
      if(key==="github"){
        const connect=action("Войти через GitHub","settings",async()=>{
          if(!item?.login_available){
            const missing=(item?.missing||[]).map(code=>({
              oauth_app:"OAuth-приложение GitHub (Client ID и Client Secret)",
              token_vault:"ключ шифрования OAUTH_TOKEN_ENCRYPTION_KEY",
              callback_and_consent:"callback для авторизации"
            })[code]||code);
            alert("GitHub OAuth пока нельзя запустить. На сервере требуется: "+(missing.join(", ")||"проверка настройки")+". Пароли и ключи в чат не отправляй.");
            return;
          }
          connect.disabled=true;
          try{
            const response=await api("/api/accounts/github/start",{
              method:"POST",body:JSON.stringify({})
            });
            if(response.authorization_url)window.location.assign(response.authorization_url);
          }catch(error){connect.disabled=false;alert(friendly(error));}
        },"secondary-button");
        connect.title=item?.login_available?"Подключить аккаунт через GitHub":"Проверить настройку GitHub OAuth";
        row.append(connect);
        if(item?.connected){
          const preview=action("Мои GitHub-подписки","search",async()=>{
            preview.disabled=true;
            const results=el("div","connection-guide");
            results.append(el("strong","","Репозитории GitHub — предпросмотр"));
            for(const collection of ["starred","watching"]){
              const load=action(collection==="starred"?"Избранные (Starred)":"Отслеживаемые (Watching)","search",async()=>{
                load.disabled=true;
                try{
                  const data=await api("/api/accounts/github/subscriptions?collection="+collection);
                  results.replaceChildren(el("strong","",collection==="starred"?"Starred":"Watching"));
                  if(!data.repositories?.length)results.append(el("p","","Публичные репозитории не найдены или доступ ограничен."));
                  for(const repository of (data.repositories||[])){
                    const entry=el("div","capability-row");
                    entry.append(el("strong","",repository.full_name));
                    entry.append(el("span","",repository.description||""));
                    const add=action("Добавить в источники","plus",async()=>{
                      add.disabled=true;
                      try{
                        await api("/api/public-sources/add",{
                          method:"POST",body:JSON.stringify({kind:"github",value:repository.full_name,topic:""})
                        });
                        add.lastElementChild.textContent="Добавлено";
                      }catch(error){add.disabled=false;alert(friendly(error));}
                    },"secondary-button");
                    entry.append(add);results.append(entry);
                  }
                  results.append(load);
                  load.disabled=false;
                }catch(error){load.disabled=false;alert(friendly(error));}
              },"secondary-button");
              results.append(load);
            }
            row.append(results);preview.disabled=false;
          },"secondary-button");
          row.append(preview);
          const disconnect=action("Отключить GitHub","close",async()=>{
            if(!window.confirm("Удалить локальный токен GitHub из ОСВЕД? Ранее добавленные источники сохранятся. Разрешение в GitHub нужно отозвать отдельно."))return;
            disconnect.disabled=true;
            try{
              const accountId=(item.account_ids||[])[0];
              if(!accountId)throw Error("github_not_connected");
              const outcome=await api("/api/accounts/github/disconnect",{
                method:"POST",body:JSON.stringify({account_id:accountId})
              });
              if(outcome.ok){
                state.accountStatus=await api("/api/accounts/status");
                render();
                alert("GitHub отключён в ОСВЕД. Для полного отзыва разрешения открой GitHub → Settings → Applications → Authorized OAuth Apps.");
              }
            }catch(error){disconnect.disabled=false;alert(friendly(error));}
          },"secondary-button");
          row.append(disconnect);
        }
      }else{
        const pending=el("button","","Войти через YouTube");
        pending.type="button";
        pending.title="Показать статус подключения YouTube";
        pending.addEventListener("click",()=>alert("YouTube OAuth пока разрабатывается. Кнопка входа будет активирована после реализации безопасного callback Google и проверки разрешений."));
        row.append(pending);
      }
      accounts.append(row);
    }
    accounts.append(el("p","","X, Reddit и импорт личных Telegram-подписок — последующие этапы. Пароли и cookies ОСВЕД не запрашивает."));
    $("#section-tools").append(accounts);
    panel.append(el("p","","Источник данных: текущая SQLite ОСВЕД. Оформление — светлая бело-синяя и тёмная серо-синяя темы."));
    const themeButton=action("Сменить тему","moon",()=>{
      theme(document.documentElement.dataset.theme==="dark"?"light":"dark");
    },"primary-button");
    panel.append(themeButton);
    $("#section-tools").append(panel);
    note("Состояние новостного ядра","Статус: "+(health.status||"ожидает диагностики")+
      ". Последняя публикация: "+(health.last_news_at||"нет")+
      ". Генерация проверенных новостей зависит от подключённого AI-провайдера и расписания.");
  }
  if(root.children.length===0)note("Ничего не найдено","Попробуй другой поисковый запрос.");
}
function showDialog(item,bodyNode){
  $("#dialog-label").textContent=item.kind==="radar"?"СИГНАЛ · НЕПРОВЕРЕНО":item.kind==="video"?"МЕДИАЛАБ":"СТАТЬЯ / ПУБЛИКАЦИЯ";
  $("#dialog-title").textContent=item.title||"Материал";
  $("#dialog-body").replaceChildren(bodyNode);
  const links=$("#dialog-links");
  links.replaceChildren();
  const sources=Array.isArray(item.sources)?item.sources:[];
  for(const source of sources){
    const url=external(source.url,source.title||"Первоисточник");
    if(url)links.append(url);
  }
  if(!sources.length){
    const url=external(item.url,"Открыть полный оригинал");
    if(url)links.append(url);
  }
  $("#dialog-overlay").hidden=false;
  $("#dialog-close").focus();
  document.body.style.overflow="hidden";
}
async function openArticle(item,kind){
  const body=el("div","dialog-body");
  body.append(el("p","","Загружаю материал и ссылки на источники…"));
  showDialog(item,body);
  try{
    const url=kind==="radar"?"/api/radar/"+item.id:"/api/article/"+encodeURIComponent(kind)+"/"+item.id;
    const result=await api(url);
    const detail=result.item;
    if(!detail)throw Error("not_found");
    const content=detail.content||{};
    body.replaceChildren();
    const snippet=content.article||content.context||content.brief||detail.body_html;
    if(snippet){
      const rich=el("div","dialog-body");
      // This HTML is sanitized by app.web.content.safe_html on the server.
      rich.innerHTML=snippet;
      body.append(rich);
    }else{
      body.append(el("p","",detail.summary||"Полная статья доступна на сайте первоисточника."));
    }
    if(!content.article&&kind==="news"){
      body.append(el("p","caption","Полная расширенная статья пока не подготовлена. Выше — сохранённый материал ОСВЕД."));
    }
    if((detail.language||item.language)==="original"||
       (!containsCyrillic(detail.title)&&!containsCyrillic(detail.summary))){
      const info=el("p","language-notice",
        "Материал сохранён на языке первоисточника. Достоверный перевод на русский пока недоступен: ОСВЕД не подменяет его догадками.");
      body.prepend(info);
    }
    body.append(readingPanel(detail,kind));
    showDialog({...detail,kind},body);
  }catch(error){
    body.replaceChildren(el("p","",friendly(error)+" Открой исходную публикацию через ссылку на карточке."));
  }
}
function closeDialog(){
  $("#dialog-overlay").hidden=true;
  document.body.style.overflow="";
}
$("#dialog-close").addEventListener("click",closeDialog);
$("#dialog-overlay").addEventListener("click",event=>{
  if(event.target===$("#dialog-overlay"))closeDialog();
});
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"&&!$("#dialog-overlay").hidden)closeDialog();
});
function mediaTools(){
  const panel=el("div","panel");
  panel.append(el("h2","","Выжимка YouTube"));
  if(state.capabilities?.video){
    const ready=state.capabilities.video.ready;
    const msg=ready?"Генерация по новым роликам настроена.":
      "Создание новых выжимок пока недоступно: "+(errors[state.capabilities.video.reason]||"требуется настройка серверных сервисов")+
      " Уже сохранённые выжимки можно открыть бесплатно.";
    panel.append(el("p",ready?"capability-ready":"capability-warning",msg));
  }
  panel.append(el("p","","Вставь ссылку на ролик. ОСВЕД проверит готовые резюме и при подключённом AI-провайдере сможет подготовить новый пересказ по субтитрам. Без субтитров содержание не выдумывается."));
  const form=el("form","media-form");
  form.id="youtube-form";
  const input=el("input");input.id="youtube-url";input.type="url";input.required=true;
  input.placeholder="https://www.youtube.com/watch?v=…";
  input.setAttribute("aria-label","Ссылка YouTube");
  const button=el("button","primary-button");
  button.type="submit";button.append(ICON("spark"),el("span","","Сделать выжимку"));
  form.append(input,button);
  const output=el("div","media-result");output.id="youtube-result";output.setAttribute("role","status");
  form.addEventListener("submit",async event=>{
    event.preventDefault();
    button.disabled=true;output.textContent="Проверяю ссылку и сохранённые резюме…";
    try{
      const result=await api("/api/video/summary",{
        method:"POST",body:JSON.stringify({url:input.value})
      });
      if(result.status==="ready"){output.textContent=result.text||"Сохранённый результат пуст.";return;}
      if(!result.job_id)throw Error("Invalid video job");
      output.textContent="Получаю субтитры и составляю выжимку. Не закрывай раздел, пока обрабатывается запрос.";
      const job=result.job_id;
      // Bounded polling. A restart will never repeat a paid generation automatically.
      for(let step=0;step<45;step++){
        await new Promise(resolve=>setTimeout(resolve,2000));
        const progress=await api("/api/video/jobs/"+encodeURIComponent(job));
        if(progress.status==="ready"){output.textContent=progress.text||"Выжимка подготовлена.";return;}
        if(progress.status==="failed"){output.textContent=errors[progress.error]||"Обработка не удалась: "+progress.error;return;}
      }
      output.textContent="Обработка ещё продолжается. Повторно платить за генерацию не нужно; проверяй кэш позже.";
    }catch(error){output.textContent=friendly(error);}
    finally{button.disabled=false;}
  });
  panel.append(form,output);
  $("#section-tools").append(panel);
}
function studioTools(){
  const panel=el("div","panel");
  panel.append(el("h2","","Конструктор обложек"));
  panel.append(el("p","","Создаёт оригинальную абстрактную векторную композицию по тексту без отправки данных на внешний AI. Сохранение в SVG. Это не фотореалистичная нейросетевая генерация."));
  const form=el("form","studio-form");
  const textarea=el("textarea");textarea.required=true;textarea.maxLength=350;textarea.minLength=4;textarea.id="studio-prompt";
  textarea.placeholder="Например: Глобальные технологии, орбиты, глубокий синий, динамика…";
  const buttons=el("div","tile-actions");
  const generate=el("button","primary-button","Создать обложку SVG");generate.type="submit";generate.id="studio-generate";
  buttons.append(generate);
  form.append(textarea,buttons);
  const result=el("div","studio-result");result.id="studio-preview";result.hidden=true;
  const download=el("button","secondary-button","Сохранить SVG");download.id="studio-download";download.hidden=true;download.type="button";
  let svgText="";
  form.addEventListener("submit",event=>{
    event.preventDefault();
    svgText=buildCover(textarea.value.trim());
    result.hidden=false;result.innerHTML=svgText;
    download.hidden=false;
  });
  download.addEventListener("click",()=>{
    const blob=new Blob([svgText],{type:"image/svg+xml;charset=utf-8"});
    const url=URL.createObjectURL(blob);
    const link=document.createElement("a");link.href=url;link.download="osved-cover.svg";
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),500);
  });
  panel.append(form,result,download,el("p","caption","Для AI-картинок потребуется подключение проверенного генератора изображений. Сейчас доступна генеративная SVG-графика."));
  $("#section-tools").append(panel);
}
function buildCover(text){
  let seed=2166136261;
  for(const char of text){seed^=char.charCodeAt(0);seed=Math.imul(seed,16777619);}
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const hue=205+Math.floor(random()*30);
  let circles="";
  for(let i=0;i<29;i++){
    const cx=Math.round(random()*1200),cy=Math.round(random()*675);
    const radius=Math.round(25+random()*200);
    const opacity=(.09+random()*.19).toFixed(2);
    circles+='<circle cx="'+cx+'" cy="'+cy+'" r="'+radius+'" fill="none" stroke="#9dceff" stroke-width="'+(1+random()*3).toFixed(1)+'" opacity="'+opacity+'"/>';
  }
  let lines="";
  for(let i=0;i<14;i++){
    const y=35+i*48+Math.round(random()*20);
    lines+='<path d="M0 '+y+' Q600 '+(y-200+random()*400)+' 1200 '+(y-35)+'" stroke="#c9e5ff" stroke-width="1" opacity=".11" fill="none"/>';
  }
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" role="img" aria-label="Абстрактная обложка ОСВЕД">'+
    '<defs><linearGradient id="o" x1="0" y1="0" x2="1" y2="1"><stop stop-color="hsl('+hue+',70%,9%)"/><stop offset="1" stop-color="hsl('+(hue+18)+',70%,30%)"/></linearGradient>'+
    '<radialGradient id="g"><stop stop-color="#4f9dff" stop-opacity=".62"/><stop offset="1" stop-color="#4f9dff" stop-opacity="0"/></radialGradient></defs>'+
    '<rect width="1200" height="675" fill="url(#o)"/><circle cx="'+Math.round(random()*650+280)+'" cy="330" r="470" fill="url(#g)"/>'+lines+circles+
    '<path d="M80 550h1040" stroke="#89bdff" stroke-opacity=".5"/>'+
    '<text x="80" y="92" font-size="24" font-family="sans-serif" font-weight="700" fill="#b8d8ff" letter-spacing="9">OSVED / RESEARCH</text>'+
    '<text x="80" y="612" font-size="23" font-family="sans-serif" fill="#dbeeff" letter-spacing="5">INTELLIGENCE · VISUAL NOTES</text></svg>';
}
async function loadDashboard(){
  const data=await api("/api/overview");
  if(!data||!Array.isArray(data.feed)||!Array.isArray(data.radar)||!Array.isArray(data.sources)||!data.health){
    throw Error("invalid dashboard payload");
  }
  state.data=data;
  try{state.capabilities=await api("/api/capabilities");}
  catch(_){state.capabilities=null;}
  try{state.aiModels=await api("/api/ai/models");}
  catch(_){state.aiModels=null;}
  try{state.accountStatus=await api("/api/accounts/status");}
  catch(_){state.accountStatus=null;}
  render();showShell();
}
async function refresh(){
  try{await loadDashboard();}
  catch(error){
    if(error.status===401){
      state.csrf="";showAuth("Сессия закончилась. Получи новый код в Telegram.");
    }else{
      // Keep old data and usable buttons in case of an intermittent API error.
      $("#result-count").textContent="Не удалось обновить: "+friendly(error);
    }
  }
}
async function start(){
  // A valid owner cookie takes precedence even inside Telegram. Reposting old
  // initData on every reload could fail its ten-minute validity check.
  try{
    const prior=await api("/api/session");
    state.csrf=prior.csrf;
    await loadDashboard();
    return;
  }catch(error){
    if(error.status!==401){
      showAuth("Не удалось проверить сохранённый вход. Проверь соединение и обнови страницу.");
      return;
    }
  }
  if(!tg||!tg.initData){
    showAuth("Войди по одноразовому коду из Telegram. На этом устройстве вход сохранится на 30 дней.");
    return;
  }
  try{
    tg.ready();tg.expand();
    const result=await api("/api/session",{
      method:"POST",body:JSON.stringify({init_data:tg.initData})
    });
    state.csrf=result.csrf;
    await loadDashboard();
  }catch(_){
    showAuth("Telegram не подтвердил новый вход. Получи одноразовый код в боте.");
  }
}
$("#code-login-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const input=$("#login-code"),button=$("#code-login-submit");
  const code=input.value.trim();
  if(!/^[0-9]{12}$/.test(code)){showAuth("Введи 12 цифр кода из Telegram.");return;}
  button.disabled=true;showAuth("Проверяю код…");
  try{
    const result=await api("/api/code-login",{method:"POST",body:JSON.stringify({code})});
    state.csrf=result.csrf;input.value="";
    await loadDashboard();
  }catch(error){showAuth(error.status===401?"Код недействителен или уже использован. Получи новый в боте.":friendly(error));}
  finally{button.disabled=false;}
});
document.querySelectorAll(".nav-link").forEach(button=>button.addEventListener("click",()=>{
  state.section=button.dataset.section;state.query="";$("#search").value="";
  render();window.scrollTo({top:0,behavior:"instant"});
}));
$("#search").addEventListener("input",event=>{
  state.query=event.target.value.trim().toLowerCase();render();
});
$("#refresh").addEventListener("click",refresh);
$("#logout").addEventListener("click",async()=>{
  try{await api("/api/logout",{method:"POST",body:"{}"});}catch(_){}
  state.csrf="";state.data=null;state.section="overview";closeDialog();
  showAuth("Ты вышел. Для нового входа запроси код в Telegram.");
});
$("#current-date").textContent=new Intl.DateTimeFormat("ru-RU",{dateStyle:"long"}).format(new Date());
start();
