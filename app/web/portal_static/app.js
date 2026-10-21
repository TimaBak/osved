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
const state={data:null,csrf:"",section:"overview",query:"",videoJob:null};
const tg=window.Telegram&&window.Telegram.WebApp;
const labels={
  overview:["Информационный обзор","Новости, события, источники и аналитика — всё в одном месте."],
  feed:["Моя лента","Проверенные материалы, подробности и первоисточники."],
  radar:["Радар событий","Публикации на этапе сбора и проверки фактов."],
  saved:["Избранное","Сохранённые материалы из кабинета и Telegram."],
  sources:["Источники","Твой реестр наблюдения и включённые каналы."],
  media:["Медиалаб","Видео YouTube, расшифровки и смысловые выжимки."],
  studio:["Студия иллюстраций","Генеративные SVG-обложки. AI-рендер потребует подключения модели."],
  settings:["Настройки","Статус платформы, оформление и доступные функции."],
};
const errors={
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
function card(item,kind){
  const type=kind==="radar"?"radar":item.kind||"news";
  const node=el("article","tile");
  const head=el("div","kicker");
  head.append(el("span","",type==="radar"?"СИГНАЛ ИСТОЧНИКА":type==="video"?"МЕДИАЛАБ":"РЕДАКЦИОННЫЙ МАТЕРИАЛ"));
  if(type==="radar")head.append(pill("НЕ ПРОВЕРЕНО","unverified"));
  node.append(head,el("h2","",item.title||"Без заголовка"));
  if(item.summary||item.source||item.source_name){
    node.append(el("p","",item.summary||sourceName(item)));
  }
  node.append(el("span","tile-meta",sourceName(item)));
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
  node.append(actions);
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
function render(){
  if(!state.data)return;
  const {feed,radar,sources,health}=state.data;
  const all=Array.isArray(feed)?feed:[];
  const signals=Array.isArray(radar)?radar:[];
  const streams=Array.isArray(sources)?sources:[];
  const news=all.filter(x=>x.kind==="news");
  const video=all.filter(x=>x.kind==="video");
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
    section==="feed"?news.length:section==="radar"?signals.length:section==="saved"?saved.length:section==="sources"?streams.length:news.length+signals.length
  )+" материалов / объектов";
  if(section==="overview"){
    if(!news.length)note("Информационная картина","Проверенные публикации ещё не готовы. Ниже доступны сигналы из реальных источников. Это не готовые новости.");
    add(news.slice(0,5),"feed");
    add(video.slice(0,3),"feed");
    if(signals.length){
      root.append(el("div","statusline","СИГНАЛЫ ИСТОЧНИКОВ · НЕПРОВЕРЕННЫЕ"));
      add(signals.slice(0,9),"radar");
    }
  }else if(section==="feed"){
    if(!news.length){
      note("Проверенных карточек пока нет","Лента формируется после проверки доказательств. Ниже реальные сообщения из источников, которые ещё не прошли проверку.");
      if(signals.length){
        root.append(el("div","statusline","СИГНАЛЫ ИСТОЧНИКОВ · НЕПРОВЕРЕННЫЕ"));
        add(signals.slice(0,12),"radar");
      }
    }else add(news,"feed");
  }else if(section==="radar"){
    if(!signals.length)note("Радар пока пуст","Новые сигналы появятся после следующего сбора источников.");
    else add(signals,"radar");
  }else if(section==="saved"){
    if(!saved.length)note("Сохранений пока нет","В ленте нажми «Сохранить» на нужном материале.");
    else add(saved,"feed");
  }else if(section==="sources"){
    if(!streams.length)note("Источников нет","Добавление источников сейчас выполняется в Telegram.");
    filter(streams).forEach(s=>{
      const tile=el("article","tile");
      tile.append(el("div","kicker",s.kind||"ИСТОЧНИК"),el("h2","",s.name||s.id));
      tile.append(pill(s.enabled?"ВКЛЮЧЁН":"ПАУЗА",s.enabled?"tag":"tag off"));
      const actions=el("div","tile-actions");
      const button=action(s.enabled?"Приостановить":"Включить","settings",async()=>{
        button.disabled=true;
        try{
          const result=await api("/api/source",{method:"POST",body:JSON.stringify({id:s.id,enabled:!s.enabled})});
          s.enabled=result.enabled;render();
        }catch(error){button.lastElementChild.textContent=friendly(error);}
        finally{button.disabled=false;}
      });
      actions.append(button);
      tile.append(actions);root.append(tile);
    });
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
  state.data=data;render();showShell();
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
  if(!tg||!tg.initData){
    try{
      const prior=await api("/api/session");state.csrf=prior.csrf;
      await loadDashboard();return;
    }catch(_){showAuth("Входи по одноразовому коду из бота ОСВЕД. Код действует 5 минут.");}
    return;
  }
  try{
    tg.ready();tg.expand();
    const result=await api("/api/session",{method:"POST",body:JSON.stringify({init_data:tg.initData})});
    state.csrf=result.csrf;
    await loadDashboard();
  }catch(_){showAuth("Автоматический вход Telegram не завершён. Можно войти по одноразовому коду.");}
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
