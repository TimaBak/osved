"use strict";
const $ = (q) => document.querySelector(q);
const el = (tag, cls, value) => {const node=document.createElement(tag);if(cls)node.className=cls;if(value!==undefined)node.textContent=String(value);return node;};
const tg = window.Telegram && window.Telegram.WebApp;
const state = {data:null,csrf:"",section:"overview"};
const titles={overview:["Информационный обзор","Факты, события и аналитика — по твоим источникам."],feed:["Моя лента","Только проверенные редакционные материалы с источниками."],radar:["Радар событий","Предварительные сигналы: не прошли проверку фактов."],sources:["Источники","Единый реестр наблюдаемых источников."],saved:["Избранное","Материалы, сохранённые в Telegram или здесь."],media:["Медиалаб","Видео и сохранённые смысловые материалы."],settings:["Настройки","Состояние конвейера и персональных данных."]};
async function api(url,opts={}){const response=await fetch(url,{credentials:"same-origin",...opts,headers:{"Content-Type":"application/json",...(opts.body?{"X-CSRF-Token":state.csrf}:{}),...(opts.headers||{})}});if(!response.ok)throw Error("HTTP "+response.status);return response.json();}
function showAuth(message){$("#auth").hidden=false;$("#shell").hidden=true;$("#login-state").textContent=message;}
function showShell(){$("#auth").hidden=true;$("#shell").hidden=false;}
function metric(name,value,caption){const card=el("div","metric");card.append(el("label","",name),el("strong","",value),el("small","",caption));return card;}
function decorateCard(item,kind){const card=el("article","tile");const kick=el("div","kicker");kick.append(el("span","",kind==="radar"?"СИГНАЛ · ПРОВЕРКА НЕ ЗАВЕРШЕНА":(item.kind==="video"?"МЕДИАЛАБ":"ПРОВЕРЕННЫЙ МАТЕРИАЛ")));if(kind==="radar")kick.append(el("span","unverified","НЕ ПРОВЕРЕНО"));card.append(kick,el("h2","",item.title||"Без заголовка"),el("p","",item.summary||item.source||""));const actions=el("div","tile-actions");if(item.url&&/^https:\/\//.test(item.url)){const a=el("a","secondary","Первоисточник ↗");a.href=item.url;a.target="_blank";a.rel="noopener noreferrer";actions.append(a);}if(kind!=="radar"){const button=el("button","",item.saved?"★ Сохранено":"☆ Сохранить");button.addEventListener("click",async()=>{try{const next=!item.saved;await api("/api/bookmark",{method:"POST",body:JSON.stringify({kind:item.kind,id:item.id,saved:next})});item.saved=next;button.textContent=next?"★ Сохранено":"☆ Сохранить";}catch(_){button.textContent="Ошибка сохранения";}});actions.append(button);}card.append(actions);return card;}
function empty(title,detail){const div=el("div","empty");div.append(el("h2","",title),el("p","",detail));return div;}
function heading(section){const title=titles[section];$("#page-title").textContent=title[0];$("#page-description").textContent=title[1];$("#crumb").textContent=title[0].toUpperCase();document.querySelectorAll(".nav-link").forEach(b=>b.classList.toggle("selected",b.dataset.section===section));}
function render(){if(!state.data)return;const {feed,radar,sources,health}=state.data;const news=feed.filter(x=>x.kind==="news"), videos=feed.filter(x=>x.kind==="video"), saved=feed.filter(x=>x.saved);const metrics=$("#metrics"),root=$("#content");metrics.replaceChildren();root.replaceChildren();metrics.append(metric("Проверенные новости",news.length,"Присутствуют в общей базе"),metric("Сигналы радара",radar.length,"Не являются проверенными новостями"),metric("Источники",sources.filter(x=>x.enabled).length,"Включено"),metric("Состояние публикаций",health.status==="ok"&&health.news_24h>0?"LIVE":"—","Новостей за 24 часа: "+health.news_24h));const section=state.section;heading(section);if(section==="overview"){root.append(empty("Твоя информационная картина",news.length?"Ниже — последние проверенные материалы.":"Пока нет выпущенных проверенных новостей. Сигналы можно посмотреть в разделе «Радар». Непроверенные факты не выдаём за новости."));[...news,...videos].slice(0,5).forEach(x=>root.append(decorateCard(x,"feed")));if(radar.length)root.append(decorateCard(radar[0],"radar"));}if(section==="feed"){if(!news.length)root.append(empty("Проверенных карточек пока нет","ОСВЕД собирает сигналы, но публикация будет доступна после фактчекинга и проверки редакционного конвейера."));news.forEach(x=>root.append(decorateCard(x,"feed")));}if(section==="radar"){if(!radar.length)root.append(empty("Сигналов нет","Новые сообщения появятся после сбора источников."));radar.forEach(x=>root.append(decorateCard(x,"radar")));}if(section==="saved"){if(!saved.length)root.append(empty("Избранное пусто","Сохрани проверенную новость в Telegram или здесь — данные синхронизируются."));saved.forEach(x=>root.append(decorateCard(x,"feed")));}if(section==="media"){if(!videos.length)root.append(empty("Материалы медиалаба пока не готовы","Добавляй видео через Telegram. Здесь появятся сохранённые результаты."));videos.forEach(x=>root.append(decorateCard(x,"feed")));}if(section==="sources"){if(!sources.length)root.append(empty("Нет источников","Добавь их через Telegram."));sources.forEach(x=>{const tile=el("article","tile");tile.append(el("div","kicker",x.kind||"ИСТОЧНИК"),el("h2","",x.name||x.id));const status=el("span","tag"+(x.enabled?"":" off"),x.enabled?"ВКЛЮЧЁН":"ПАУЗА");tile.append(status);const actions=el("div","tile-actions");const button=el("button","",x.enabled?"Приостановить":"Включить");button.addEventListener("click",async()=>{try{const result=await api("/api/source",{method:"POST",body:JSON.stringify({id:x.id,enabled:!x.enabled})});x.enabled=result.enabled;render();}catch(_){button.textContent="Ошибка";}});actions.append(button);tile.append(actions);root.append(tile);});}if(section==="settings"){root.append(empty("Статус информационного ядра","Состояние: "+health.status+". Последняя новость: "+(health.last_news_at||"отсутствует")+". Задача: получить валидную карточку и доставить её в Telegram. Настройки источников доступны в соседнем разделе."));}}
async function loadDashboard(){
  const data=await api("/api/overview");
  if(!data || !Array.isArray(data.feed) || !Array.isArray(data.radar) || !Array.isArray(data.sources) || !data.health){
    throw new Error("invalid_dashboard_payload");
  }
  state.data=data;
  render();
  showShell();
}
async function refresh(){
  try{await loadDashboard();}
  catch(error){
    if(String(error.message).includes("401")){state.csrf="";showAuth("Сессия закончилась. Войди по новому коду из Telegram.");}
    else{showAuth("Не удалось загрузить данные кабинета. Проверь подключение и открой сайт заново.");}
  }
}
async function start(){
  // Direct browser and Telegram WebApp are two supported paths. Never render
  // private sections before a validated session and API response.
  if(!tg || !tg.initData){
    showAuth("Для входа с компьютера запроси код в боте ОСВЕД и введи его выше.");
    return;
  }
  try{
    tg.ready();
    tg.expand();
    const login=await api("/api/session",{
      method:"POST",body:JSON.stringify({init_data:tg.initData})
    });
    state.csrf=login.csrf;
    await loadDashboard();
  }catch(error){
    showAuth("Вход через Telegram не завершён. Можешь получить одноразовый код в боте и войти вручную.");
  }
}
$("#code-login-form").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const input=$("#login-code"),button=$("#code-login-submit");
  const code=input.value.trim();
  if(!/^[0-9]{12}$/.test(code)){showAuth("Введите 12 цифр кода из Telegram.");return;}
  button.disabled=true;
  showAuth("Проверяю одноразовый код…");
  try{
    const login=await api("/api/code-login",{
      method:"POST",body:JSON.stringify({code})
    });
    state.csrf=login.csrf;
    input.value="";
    await loadDashboard();
  }catch(error){
    const rejected=String(error.message).includes("401");
    showAuth(rejected?"Код недействителен, истёк или уже использован. Получи новый в боте.":"Не получилось открыть кабинет. Повтори попытку или проверь соединение.");
  }finally{button.disabled=false;}
});
document.querySelectorAll(".nav-link").forEach(b=>b.addEventListener("click",()=>{
  state.section=b.dataset.section;
  render();
  window.scrollTo({top:0,behavior:"instant"});
}));
$("#refresh").addEventListener("click",refresh);
$("#logout").addEventListener("click",async()=>{
  try{await api("/api/logout",{method:"POST",body:"{}"});}catch(_){}
  state.csrf="";state.data=null;
  showAuth("Ты вышел из кабинета. Для нового входа получи код в Telegram.");
});
$("#current-date").textContent=new Intl.DateTimeFormat("ru-RU",{dateStyle:"long"}).format(new Date());
start();
