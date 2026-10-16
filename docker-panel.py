#!/usr/bin/env python3
"""
极简 Docker 管理面板：容器 / 镜像 / 卷
用法: python3 docker-panel.py [端口号]
"""
import http.server, socketserver, socket, os, sys
from urllib.parse import unquote

def find_socket():
    for p in ["/var/run/docker.sock", os.path.expanduser("~/.docker/run/docker.sock")]:
        if os.path.exists(p):
            return p
    return None

DOCKER_SOCKET = find_socket()
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9999

def decode_chunked(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        j = data.find(b'\r\n', i)
        if j == -1: break
        try:
            size = int(data[i:j].split(b';')[0], 16)
        except ValueError:
            break
        if size == 0: break
        out += data[j + 2 : j + 2 + size]
        i = j + 2 + size + 2
    return bytes(out)

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Docker</title>
<style>
:root{
  --bg:#0a0a0b; --card:#141417; --card-hover:#1a1a1f; --border:#232329; --border-hover:#2e2e36;
  --text:#e4e4e7; --text-dim:#a1a1aa; --muted:#71717a;
  --green:#22c55e; --green-glow:rgba(34,197,94,.15);
  --red:#f87171; --red-bg:#2a1516; --red-border:#5a2020;
  --blue:#60a5fa; --blue-bg:#1e3a5f; --blue-border:#2a4a73;
  --btn:#1c1c20; --btn-hover:#26262b;
  --input-bg:#0a0a0b;
  --scroll-thumb:#2e2e36; --scroll-thumb-hover:#3f3f46;
  --code-bg:#0a0a0b;
}
[data-theme="light"]{
  --bg:#f6f6f7; --card:#ffffff; --card-hover:#fafafa; --border:#e4e4e7; --border-hover:#d4d4d8;
  --text:#18181b; --text-dim:#52525b; --muted:#71717a;
  --green:#16a34a; --green-glow:rgba(22,163,74,.15);
  --red:#dc2626; --red-bg:#fef2f2; --red-border:#fecaca;
  --blue:#2563eb; --blue-bg:#eff6ff; --blue-border:#bfdbfe;
  --btn:#ffffff; --btn-hover:#f4f4f5;
  --input-bg:#ffffff;
  --scroll-thumb:#d4d4d8; --scroll-thumb-hover:#a1a1aa;
  --code-bg:#f9f9fa;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;
  background:var(--bg);color:var(--text);font-size:14px;-webkit-font-smoothing:antialiased;
  transition:background .2s,color .2s}
html.theme-switching *,html.theme-switching *::before,html.theme-switching *::after{transition:none!important}

/* 美化滚动条 */
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--scroll-thumb);border-radius:10px;
  border:2px solid transparent;background-clip:padding-box;transition:background .15s}
::-webkit-scrollbar-thumb:hover{background:var(--scroll-thumb-hover);background-clip:padding-box;
  border:2px solid transparent}
::-webkit-scrollbar-corner{background:transparent}

header{display:flex;align-items:center;justify-content:space-between;padding:14px 28px;
  border-bottom:1px solid var(--border);position:sticky;top:0;
  background:var(--bg);z-index:10;gap:20px;flex-wrap:wrap}
.tabs{display:flex;gap:3px;background:var(--btn);padding:3px;border-radius:9px;border:1px solid var(--border)}
.tabs button{background:transparent;border:none;padding:6px 16px;border-radius:6px;
  color:var(--muted);font-size:13px;font-weight:500;cursor:pointer;transition:.15s}
.tabs button.active{background:var(--card);color:var(--text);box-shadow:0 1px 3px rgba(0,0,0,.1)}
.tabs button:hover:not(.active){color:var(--text)}
.right{display:flex;align-items:center;gap:10px}
.count{color:var(--muted);font-size:13px}
button{font:inherit;font-size:13px;color:var(--text);background:var(--btn);border:1px solid var(--border);
  padding:7px 14px;border-radius:7px;cursor:pointer;transition:.15s}
button:hover{background:var(--btn-hover);border-color:var(--border-hover)}
button:active{transform:scale(.97)}
button:disabled{opacity:.4;cursor:default;transform:none}
button.primary{background:var(--blue-bg);border-color:var(--blue-border);color:var(--blue)}
button.primary:hover{filter:brightness(1.1)}
button.danger:hover{background:var(--red-bg);border-color:var(--red-border);color:var(--red)}
.icon-btn{width:34px;height:34px;padding:0;display:flex;align-items:center;justify-content:center;
  font-size:15px;border-radius:8px}

main{padding:28px;max-width:1240px;margin:0 auto;display:flex;justify-content:center}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  justify-content:center;gap:14px;width:100%}

.card{background:var(--card);border:1px solid var(--border);border-radius:11px;
  padding:16px;transition:.15s;animation:fade .25s ease-out}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.card:hover{border-color:var(--border-hover);background:var(--card-hover)}
.card-head{display:flex;align-items:center;gap:9px;margin-bottom:14px}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;transition:.15s}
.dot.on{background:var(--green);box-shadow:0 0 0 3px var(--green-glow)}
.dot.off{background:var(--scroll-thumb-hover)}
.name{font-weight:600;font-size:14px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.status{font-size:11px;color:var(--muted);font-family:ui-monospace,monospace;flex-shrink:0}
.meta{display:flex;gap:10px;margin-bottom:7px;font-size:12px;align-items:baseline}
.meta .label{color:var(--muted);width:42px;flex-shrink:0}
.meta .value{color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11.5px}
.actions{display:flex;gap:7px;margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}
.actions button{flex:1;padding:6px 8px;font-size:12px}
.empty{text-align:center;padding:100px 20px;color:var(--muted);width:100%}
.empty p{margin-top:8px;font-size:13px}

.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;
  justify-content:center;padding:24px;z-index:100;backdrop-filter:blur(4px);animation:fade .15s}
.modal.show{display:flex}
.modal-box{background:var(--card);border:1px solid var(--border);border-radius:13px;
  width:100%;max-width:900px;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;
  box-shadow:0 20px 60px rgba(0,0,0,.4)}
.modal-box.small{max-width:440px}
.modal-head{display:flex;align-items:center;justify-content:space-between;
  padding:14px 18px;border-bottom:1px solid var(--border);flex-shrink:0}
.modal-head h2{font-size:14px;font-weight:600}
.modal-head .sub{color:var(--muted);font-size:12px;margin-left:10px}
.modal-body{padding:18px;display:flex;flex-direction:column;gap:14px;overflow-y:auto}
.modal-body label{font-size:12px;color:var(--muted);margin-bottom:6px;display:block}
.modal-body input{width:100%;background:var(--input-bg);border:1px solid var(--border);border-radius:7px;
  padding:9px 12px;color:var(--text);font:inherit;font-size:13px;outline:none;transition:.15s}
.modal-body input:focus{border-color:var(--blue);box-shadow:0 0 0 3px color-mix(in srgb,var(--blue) 20%,transparent)}
.modal-body .hint{font-size:12px;color:var(--muted);line-height:1.5}
.modal-body .target-name{font-family:ui-monospace,monospace;font-size:13px;color:var(--text);
  background:var(--code-bg);padding:10px 12px;border-radius:7px;border:1px solid var(--border);
  word-break:break-all;user-select:all}
.modal-foot{display:flex;justify-content:flex-end;gap:8px;padding:14px 18px;
  border-top:1px solid var(--border);flex-shrink:0}

pre{flex:1;overflow:auto;padding:16px 18px;font-family:ui-monospace,"SF Mono",Menlo,monospace;
  font-size:12px;line-height:1.65;color:var(--text-dim);background:var(--code-bg);margin:0;
  white-space:pre-wrap;word-break:break-all;border-radius:0}
pre::-webkit-scrollbar{width:12px;height:12px}
pre::-webkit-scrollbar-thumb{background:var(--scroll-thumb);border-radius:10px;
  border:3px solid var(--code-bg);background-clip:padding-box}
pre::-webkit-scrollbar-thumb:hover{background:var(--scroll-thumb-hover);background-clip:padding-box;
  border:3px solid var(--code-bg)}

.toast{position:fixed;top:max(24px,env(safe-area-inset-top));left:50%;transform:translateX(-50%) translateY(-80px);
  background:var(--card);border:1px solid var(--border);padding:10px 18px;border-radius:9px;
  font-size:13px;transition:.25s;z-index:200;opacity:0;pointer-events:none;max-width:80vw;
  box-shadow:0 10px 30px rgba(0,0,0,.25)}
.toast.show{transform:translateX(-50%) translateY(0);opacity:1}
.toast.err{border-color:var(--red-border);color:var(--red)}
</style>
</head>
<body>
<header>
  <div class="tabs">
    <button data-tab="containers" class="active">容器</button>
    <button data-tab="images">镜像</button>
    <button data-tab="volumes">数据卷</button>
  </div>
  <div class="right">
    <span class="count" id="count"></span>
    <button id="action-btn" class="primary" onclick="primaryAction()" style="display:none"></button>
    <button class="icon-btn" onclick="toggleTheme()" title="切换主题" id="theme-btn">☀</button>
    <button onclick="load()">刷新</button>
  </div>
</header>

<main><div class="grid" id="view"></div></main>

<div class="modal" id="log-modal">
  <div class="modal-box">
    <div class="modal-head">
      <div><h2 id="log-title"></h2><span class="sub" id="log-sub"></span></div>
      <button onclick="closeLog()">关闭</button>
    </div>
    <pre id="log-content"></pre>
  </div>
</div>

<div class="modal" id="input-modal">
  <div class="modal-box small">
    <div class="modal-head"><h2 id="input-title"></h2></div>
    <div class="modal-body">
      <div><label id="input-label"></label>
      <input id="input-field" autocomplete="off"></div>
    </div>
    <div class="modal-foot">
      <button onclick="closeInput()">取消</button>
      <button class="primary" onclick="confirmInput()">确定</button>
    </div>
  </div>
</div>

<div class="modal" id="del-modal">
  <div class="modal-box small">
    <div class="modal-head"><h2 id="del-title">删除确认</h2></div>
    <div class="modal-body">
      <div class="hint" id="del-hint"></div>
      <div class="target-name" id="del-target"></div>
      <div id="del-input-wrap">
        <label id="del-label"></label>
        <input id="del-input" autocomplete="off" placeholder="">
      </div>
    </div>
    <div class="modal-foot">
      <button onclick="closeDel()">取消</button>
      <button class="danger" id="del-confirm" onclick="confirmDel()" disabled>确认删除</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const state = { tab:'containers', data:{containers:[],images:[],volumes:[]},
  inputCb:null, delCb:null, delForceCb:null, delMode:'type', delName:'' };

// ---------- 主题 ----------
let themeSwitchFrame = 0;
function applyTheme(t){
  document.documentElement.classList.add('theme-switching');
  document.documentElement.dataset.theme = t;
  $('theme-btn').textContent = t === 'dark' ? '☀' : '☾';
  try{ localStorage.setItem('dp-theme', t); }catch(_){}
  cancelAnimationFrame(themeSwitchFrame);
  themeSwitchFrame = requestAnimationFrame(() => {
    themeSwitchFrame = requestAnimationFrame(() => {
      document.documentElement.classList.remove('theme-switching');
    });
  });
}
function toggleTheme(){
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}
(function initTheme(){
  let t = 'dark';
  try{ t = localStorage.getItem('dp-theme') || 'dark'; }catch(_){}
  applyTheme(t);
})();

function toast(msg, err){
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show' + (err ? ' err' : '');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.className = 'toast', 2200);
}

async function api(path, method='GET', body){
  const opts = {method, cache:'no-store'};
  if(body !== undefined){
    opts.headers = {'Content-Type':'application/json'};
    opts.body = typeof body === 'string' ? body : JSON.stringify(body);
  }
  const res = await fetch('/api' + path, opts);
  if(!res.ok && res.status !== 304){
    let msg = res.statusText;
    try{
      const t = await res.text();
      if(t){
        try{ msg = JSON.parse(t).message || t.slice(0,200); }
        catch(_){ msg = t.slice(0,200); }
      }
    }catch(_){}
    throw new Error(msg);
  }
  return res;
}
function imageApiPath(id){
  return '/images/' + encodeURIComponent(id).replace(/%3A/gi, ':');
}
async function deleteImageAndVerify(id, force){
  await api(imageApiPath(id) + '?force=' + String(force), 'DELETE');
  let images = [];
  for(let attempt = 0; attempt < 3; attempt++){
    if(attempt) await new Promise(resolve => setTimeout(resolve, 180));
    const r = await api('/images/json?all=true');
    images = await r.json();
    if(!images.some(image => image.Id === id)) break;
  }
  state.data.images = images;
  if(state.tab === 'images') renderImages();
  if(images.some(image => image.Id === id)){
    throw new Error(force
      ? '强制删除请求已完成，但 Docker 仍返回该镜像；它可能仍被其他镜像依赖。'
      : '删除请求已完成，但 Docker 列表仍返回该镜像。');
  }
}

function fmtSize(b){
  if(b == null) return '—';
  if(b < 1024) return b + ' B';
  if(b < 1048576) return (b/1024).toFixed(1) + ' KB';
  if(b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
  return (b/1073741824).toFixed(2) + ' GB';
}
function fmtTime(ts){
  if(!ts) return '—';
  const ms = typeof ts === 'number' ? (ts < 1e12 ? ts*1000 : ts) : Date.parse(ts);
  if(isNaN(ms)) return '—';
  const diff = Math.floor((Date.now() - ms)/1000);
  if(diff < 60) return diff + ' 秒前';
  if(diff < 3600) return Math.floor(diff/60) + ' 分钟前';
  if(diff < 86400) return Math.floor(diff/3600) + ' 小时前';
  if(diff < 2592000) return Math.floor(diff/86400) + ' 天前';
  return new Date(ms).toLocaleDateString();
}
function localizeContainerStatus(status, state){
  const raw = String(status || state || '').trim();
  const time = value => value
    .replace(/\bless than a second\b/gi, '不足 1 秒')
    .replace(/\b(\d+)\s+(seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b/gi, (_, n, unit) => {
      const units = {second:'秒',minute:'分钟',hour:'小时',day:'天',week:'周',month:'个月',year:'年'};
      return n + ' ' + units[unit.toLowerCase().replace(/s$/, '')];
    })
    .replace(/\s+ago\b/i, '前')
    .trim();
  const healthLabel = value => ({
    healthy:'健康', unhealthy:'不健康', 'health: starting':'健康检查中',
  }[value.toLowerCase()] || value);

  let match = raw.match(/^Up(?:\s+(.+?))?(?:\s+\((healthy|unhealthy|health: starting)\))?$/i);
  if(match){
    const duration = match[1] ? time(match[1]) : '';
    const health = match[2] || (match[1] && match[1].match(/\((healthy|unhealthy|health: starting)\)/i)?.[1]);
    const cleanDuration = duration.replace(/\s*\((healthy|unhealthy|health: starting)\)/i, '');
    return '运行中' + (cleanDuration ? ' · 已运行 ' + cleanDuration : '') + (health ? ' · ' + healthLabel(health) : '');
  }
  match = raw.match(/^Exited\s+\((-?\d+)\)(?:\s+(.+))?$/i);
  if(match) return '已退出 · 退出码 ' + match[1] + (match[2] ? ' · ' + time(match[2]) : '');
  match = raw.match(/^Restarting(?:\s+\((\d+)\))?(?:\s+(.+))?$/i);
  if(match) return '重启中' + (match[1] ? ' · 第 ' + match[1] + ' 次' : '') + (match[2] ? ' · ' + time(match[2]) : '');

  const labels = {
    running:'运行中', created:'已创建', exited:'已退出', restarting:'重启中',
    paused:'已暂停', dead:'异常停止', removing:'正在删除',
    'removal in progress':'正在删除',
  };
  return labels[raw.toLowerCase()] || raw || '未知状态';
}

document.querySelectorAll('.tabs button').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    state.tab = b.dataset.tab;
    updateActionBtn();
    load();
  };
});

function updateActionBtn(){
  const b = $('action-btn');
  if(state.tab === 'images'){ b.textContent = '拉取镜像'; b.style.display = ''; }
  else if(state.tab === 'volumes'){ b.textContent = '新建卷'; b.style.display = ''; }
  else { b.style.display = 'none'; }
}

async function load(){
  try{
    if(state.tab === 'containers'){
      const r = await api('/containers/json?all=true');
      state.data.containers = await r.json();
    } else if(state.tab === 'images'){
      const r = await api('/images/json');
      state.data.images = await r.json();
    } else {
      const r = await api('/volumes');
      const j = await r.json();
      state.data.volumes = j.Volumes || [];
    }
    render();
  }catch(e){
    $('view').innerHTML = '<div class="empty">加载失败<p>' + esc(e.message) + '</p></div>';
  }
}

let containerPollInFlight = false;
async function pollContainers(){
  if(document.hidden || state.tab !== 'containers' || containerPollInFlight) return;
  containerPollInFlight = true;
  try{
    const r = await api('/containers/json?all=true');
    const containers = await r.json();
    if(document.hidden || state.tab !== 'containers') return;
    state.data.containers = containers;
    syncContainerCards(containers);
  }catch(_){
    // 后台同步失败不覆盖当前界面；手动刷新仍会显示错误。
  }finally{
    containerPollInFlight = false;
  }
}

function render(){
  if(state.tab === 'containers') renderContainers();
  else if(state.tab === 'images') renderImages();
  else renderVolumes();
}

function renderContainers(){
  const list = state.data.containers, v = $('view');
  $('count').textContent = list.length + ' 个容器';
  if(!list.length){ v.innerHTML = '<div class="empty">还没有容器</div>'; return; }

  v.innerHTML = list.map(containerCard).join('');
}

function containerCard(c){
  const name = (c.Names && c.Names[0] ? c.Names[0] : c.Id.slice(0,12)).replace(/^\//,'');
  const running = c.State === 'running';
  const ports = (c.Ports||[]).filter(p=>p.PublicPort).map(p=>p.PublicPort+'→'+p.PrivatePort).join(', ') || '—';
  const img = c.Image.length > 34 ? c.Image.slice(0,34)+'…' : c.Image;
  return '<div class="card" data-id="'+c.Id+'" data-name="'+esc(name)+'">'
    + '<div class="card-head">'
    +   '<span class="dot '+(running?'on':'off')+'"></span>'
    +   '<span class="name" title="'+esc(name)+'">'+esc(name)+'</span>'
    +   '<span class="status">'+esc(localizeContainerStatus(c.Status,c.State))+'</span>'
    + '</div>'
    + '<div class="meta"><span class="label">镜像</span><span class="value mono" title="'+esc(c.Image)+'">'+esc(img)+'</span></div>'
    + '<div class="meta"><span class="label">端口</span><span class="value mono">'+esc(ports)+'</span></div>'
    + '<div class="actions">'+containerActions(running)+'</div></div>';
}

function containerActions(running){
  return (running
      ? '<button data-act="stop">停止</button><button data-act="restart">重启</button>'
      : '<button data-act="start">启动</button>')
    + '<button data-act="logs">日志</button>'
    + '<button data-act="rm" class="danger">删除</button>';
}

function syncContainerCards(list){
  const view = $('view');
  const cards = new Map([...view.querySelectorAll('.card[data-id]')].map(card => [card.dataset.id, card]));
  const ids = list.map(c => c.Id);
  const structureChanged = ids.length !== cards.size || ids.some(id => !cards.has(id));
  $('count').textContent = list.length + ' 个容器';
  if(structureChanged){ renderContainers(); return; }

  for(const c of list){
    const card = cards.get(c.Id);
    const name = (c.Names && c.Names[0] ? c.Names[0] : c.Id.slice(0,12)).replace(/^\//,'');
    const running = c.State === 'running';
    const ports = (c.Ports||[]).filter(p=>p.PublicPort).map(p=>p.PublicPort+'→'+p.PrivatePort).join(', ') || '—';
    const img = c.Image.length > 34 ? c.Image.slice(0,34)+'…' : c.Image;
    card.dataset.name = name;
    const nameEl = card.querySelector('.name');
    if(nameEl.textContent !== name){ nameEl.textContent = name; nameEl.title = name; }
    const dot = card.querySelector('.dot');
    dot.classList.toggle('on', running);
    dot.classList.toggle('off', !running);
    card.querySelector('.status').textContent = localizeContainerStatus(c.Status, c.State);
    const values = card.querySelectorAll('.meta .value');
    if(values[0]){ values[0].textContent = img; values[0].title = c.Image; }
    if(values[1]) values[1].textContent = ports;
    const actions = card.querySelector('.actions');
    if((actions.querySelector('[data-act="start"]') && running) || (actions.querySelector('[data-act="stop"]') && !running)){
      actions.innerHTML = containerActions(running);
    }
  }
}

function renderImages(){
  const list = state.data.images.slice(), v = $('view');
  $('count').textContent = list.length + ' 个镜像';
  if(!list.length){ v.innerHTML = '<div class="empty">还没有镜像<p>点右上角拉取一个</p></div>'; return; }

  list.sort((a,b) => {
    const na = (a.RepoTags && a.RepoTags[0]) || 'zzz';
    const nb = (b.RepoTags && b.RepoTags[0]) || 'zzz';
    return na.localeCompare(nb);
  });

  v.innerHTML = list.map(img => {
    const tag = (img.RepoTags && img.RepoTags[0]) || '<none>:<none>';
    const isDangling = !img.RepoTags || !img.RepoTags.length;
    const shortId = img.Id.replace(/^sha256:/, '').slice(0, 12);
    const tagCount = (img.RepoTags||[]).length;
    const more = tagCount > 1 ? ' +' + (tagCount-1) : '';
    const displayName = isDangling ? shortId : tag;
    return '<div class="card" data-id="'+esc(img.Id)+'" data-tag="'+esc(tag)+'" data-name="'+esc(displayName)+'">'
      + '<div class="card-head">'
      +   '<span class="dot '+(isDangling?'off':'on')+'"></span>'
      +   '<span class="name" title="'+esc(tag)+'">'+esc(tag)+more+'</span>'
      + '</div>'
      + '<div class="meta"><span class="label">大小</span><span class="value mono">'+fmtSize(img.Size)+'</span></div>'
      + '<div class="meta"><span class="label">创建</span><span class="value">'+fmtTime(img.Created)+'</span></div>'
      + '<div class="meta"><span class="label">ID</span><span class="value mono">'+shortId+'</span></div>'
      + '<div class="actions">'
      +   '<button data-act="run-image"'+(isDangling?' disabled':'')+'>运行</button>'
      +   '<button data-act="rm-image" class="danger">删除</button>'
      + '</div></div>';
  }).join('');
}

function renderVolumes(){
  const list = state.data.volumes, v = $('view');
  $('count').textContent = list.length + ' 个卷';
  if(!list.length){ v.innerHTML = '<div class="empty">还没有数据卷</div>'; return; }

  v.innerHTML = list.map(vol => {
    const inUse = vol.UsageData && vol.UsageData.RefCount > 0;
    const mp = vol.Mountpoint || (vol.Options && vol.Options.device) || '—';
    const shortMp = mp.length > 40 ? '…' + mp.slice(-38) : mp;
    return '<div class="card" data-name="'+esc(vol.Name)+'">'
      + '<div class="card-head">'
      +   '<span class="dot '+(inUse?'on':'off')+'"></span>'
      +   '<span class="name" title="'+esc(vol.Name)+'">'+esc(vol.Name)+'</span>'
      +   (inUse ? '<span class="status">使用中</span>' : '')
      + '</div>'
      + '<div class="meta"><span class="label">驱动</span><span class="value mono">'+esc(vol.Driver)+'</span></div>'
      + '<div class="meta"><span class="label">挂载点</span><span class="value mono" title="'+esc(mp)+'">'+esc(shortMp)+'</span></div>'
      + '<div class="meta"><span class="label">创建</span><span class="value">'+fmtTime(vol.CreatedAt)+'</span></div>'
      + '<div class="actions">'
      +   '<button data-act="rm-volume" class="danger" '+(inUse?'disabled title="正在被容器使用"':'')+'>删除</button>'
      + '</div></div>';
  }).join('');
}

$('view').addEventListener('click', async e => {
  const btn = e.target.closest('button[data-act]');
  if(!btn || btn.disabled) return;
  const card = btn.closest('.card');
  const act = btn.dataset.act;

  if(state.tab === 'containers'){
    const id = card.dataset.id;
    const name = card.dataset.name;
    if(act === 'logs'){ showLogs(id, name); return; }
    if(act === 'rm'){
      openDel('删除容器', name, '容器',
        async () => api('/containers/' + id + '?force=true', 'DELETE'));
      return;
    }
    btn.disabled = true;
    try{
      if(act === 'start')        await api('/containers/' + id + '/start', 'POST');
      else if(act === 'stop')    await api('/containers/' + id + '/stop', 'POST');
      else if(act === 'restart') await api('/containers/' + id + '/restart', 'POST');
      toast('操作成功'); await load();
    }catch(err){ toast('失败: ' + err.message.slice(0,60), true); btn.disabled = false; }
  }
  else if(state.tab === 'images'){
    const tag = card.dataset.tag;
    const displayName = card.dataset.name;
    if(act === 'run-image'){
      openInput('运行镜像', '容器名', tag.split('/').pop().split(':')[0], async (name) => {
        if(!name) return;
        try{
          await api('/containers/create?name=' + encodeURIComponent(name), 'POST',
            {Image: tag});
          await api('/containers/' + encodeURIComponent(name) + '/start', 'POST');
          toast('已启动 ' + name);
          state.tab = 'containers';
          document.querySelectorAll('.tabs button').forEach(x =>
            x.classList.toggle('active', x.dataset.tab === 'containers'));
          updateActionBtn(); load();
        }catch(err){ toast('失败: ' + err.message.slice(0,80), true); }
      });
    }
    else if(act === 'rm-image'){
      const imageId = card.dataset.id;
      openDel('删除镜像', displayName, '镜像',
        () => deleteImageAndVerify(imageId, false),
        () => deleteImageAndVerify(imageId, true));
    }
  }
  else if(state.tab === 'volumes'){
    const name = card.dataset.name;
    if(act === 'rm-volume'){
      openDel('删除数据卷', name, '卷',
        async () => api('/volumes/' + encodeURIComponent(name), 'DELETE'));
    }
  }
});

async function primaryAction(){
  if(state.tab === 'images'){
    openInput('拉取镜像', '镜像名（可带 tag，如 nginx:alpine）', '', async (name) => {
      if(!name) return;
      toast('正在拉取 ' + name + '…');
      try{
        const [repo, tag] = name.includes(':') ? name.split(':') : [name, 'latest'];
        await api('/images/create?fromImage=' + encodeURIComponent(repo) +
                  '&tag=' + encodeURIComponent(tag), 'POST');
        toast('拉取完成'); load();
      }catch(e){ toast('拉取失败: ' + e.message.slice(0,80), true); }
    });
  }
  else if(state.tab === 'volumes'){
    openInput('新建数据卷', '卷名称', '', async (name) => {
      if(!name) return;
      try{
        await api('/volumes/create', 'POST', {Name: name});
        toast('已创建'); load();
      }catch(e){ toast('失败: ' + e.message.slice(0,60), true); }
    });
  }
}

// ---------- 日志 ----------
async function showLogs(id, name){
  $('log-title').textContent = name;
  $('log-sub').textContent = '加载中…';
  $('log-content').textContent = '';
  $('log-modal').classList.add('show');
  try{
    const res = await fetch('/api/containers/' + id + '/logs?stdout=1&stderr=1&tail=300');
    let text = await res.text();
    text = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');
    $('log-content').textContent = text || '（没有日志输出）';
    $('log-sub').textContent = '';
    const pre = $('log-content');
    pre.scrollTop = pre.scrollHeight;
  }catch(err){ $('log-content').textContent = '加载失败: ' + err.message; }
}
function closeLog(){ $('log-modal').classList.remove('show'); }

// ---------- 输入 ----------
function openInput(title, label, def, cb){
  $('input-title').textContent = title;
  $('input-label').textContent = label;
  $('input-field').value = def || '';
  state.inputCb = cb;
  $('input-modal').classList.add('show');
  setTimeout(() => $('input-field').focus(), 50);
}
function closeInput(){ $('input-modal').classList.remove('show'); state.inputCb = null; }
function confirmInput(){
  const v = $('input-field').value.trim();
  const cb = state.inputCb;
  closeInput();
  if(cb) cb(v);
}

// ---------- 删除确认（需输入名称） ----------
function openDel(title, name, kind, cb, forceCb=null){
  state.delCb = cb;
  state.delForceCb = forceCb;
  state.delMode = 'type';
  state.delName = name;
  $('del-title').textContent = title;
  $('del-hint').textContent = '此操作不可撤销，请确认。';
  $('del-input-wrap').hidden = false;
  $('del-target').textContent = name;
  $('del-label').textContent = '请输入 ' + kind + '名称「' + name + '」以确认删除：';
  const inp = $('del-input');
  inp.value = '';
  inp.placeholder = name;
  $('del-confirm').textContent = '确认删除';
  $('del-confirm').disabled = true;
  $('del-modal').classList.add('show');
  setTimeout(() => inp.focus(), 50);
}
function closeDel(){
  $('del-modal').classList.remove('show');
  state.delCb = null; state.delForceCb = null; state.delMode = 'type'; state.delName = '';
  $('del-input-wrap').hidden = false;
  $('del-confirm').textContent = '确认删除';
}
async function confirmDel(){
  const cb = state.delCb;
  if(!cb) return;
  const btn = $('del-confirm');
  btn.disabled = true;
  try{
    await cb();
    toast('已删除');
    closeDel();
    await load();
  }catch(err){
    const message = String(err.message || err).slice(0,180);
    if(state.delForceCb && state.delMode !== 'force' && /being used by|must be forced|列表仍返回该镜像/i.test(message)){
      state.delCb = state.delForceCb;
      state.delForceCb = null;
      state.delMode = 'force';
      $('del-hint').textContent = 'Docker 未移除该镜像，可能仍被容器或其他镜像引用。强制删除后会移除该镜像，仍要继续吗？';
      $('del-input-wrap').hidden = true;
      btn.textContent = '强制删除';
    }else{
      $('del-hint').textContent = (state.delMode === 'force' ? '强制删除失败：' : '删除失败：') + message;
    }
    btn.disabled = false;
  }
}
$('del-input').addEventListener('input', e => {
  if(state.delMode === 'force') return;
  $('del-confirm').disabled = e.target.value.trim() !== state.delName;
});
$('del-input').addEventListener('keydown', e => {
  if(e.key === 'Enter' && !$('del-confirm').disabled) confirmDel();
});

// ---------- 全局键盘 / 遮罩关闭 ----------
$('log-modal').addEventListener('click', e => { if(e.target === $('log-modal')) closeLog(); });
$('input-modal').addEventListener('click', e => { if(e.target === $('input-modal')) closeInput(); });
$('del-modal').addEventListener('click', e => { if(e.target === $('del-modal')) closeDel(); });
document.addEventListener('keydown', e => {
  if(e.key === 'Escape'){ closeLog(); closeInput(); closeDel(); }
  if(e.key === 'Enter' && $('input-modal').classList.contains('show')) confirmInput();
});

updateActionBtn();
load();
setInterval(pollContainers, 5000);
</script>
</body>
</html>
"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path.startswith('/api/'): self.proxy('GET')
        else: self.serve_html()

    def do_POST(self):   self.proxy('POST')
    def do_DELETE(self): self.proxy('DELETE')
    def do_PUT(self):    self.proxy('PUT')

    def serve_html(self):
        body = HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def proxy(self, method):
        docker_path = self.path[4:]
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else b''

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(120)
            sock.connect(DOCKER_SOCKET)
        except Exception as e:
            self.send_error(502, "Cannot connect to docker: %s" % e); return

        req = "%s %s HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: %d\r\n" % (
            method, docker_path, len(body))
        ct = self.headers.get('Content-Type')
        if ct: req += "Content-Type: %s\r\n" % ct
        req += "\r\n"

        try:
            sock.sendall(req.encode('latin-1'))
            if body: sock.sendall(body)

            chunks = []
            while True:
                data = sock.recv(65536)
                if not data: break
                chunks.append(data)
        except socket.timeout:
            self.send_error(504, "Docker timeout"); return
        finally:
            sock.close()

        raw = b''.join(chunks)
        hdr_end = raw.find(b'\r\n\r\n')
        if hdr_end == -1:
            self.send_error(502, "Bad response"); return

        headers_raw = raw[:hdr_end].decode('latin-1')
        resp_body = raw[hdr_end + 4:]
        try:
            status = int(headers_raw.split(' ', 2)[1])
        except Exception:
            self.send_error(502, "Bad status line"); return

        hdrs = {}
        for line in headers_raw.split('\r\n')[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                hdrs[k.strip().lower()] = v.strip()

        if hdrs.get('transfer-encoding', '').lower() == 'chunked':
            resp_body = decode_chunked(resp_body)

        self.send_response(status)
        self.send_header('Content-Type', hdrs.get('content-type', 'application/json'))
        self.send_header('Content-Length', str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    if not DOCKER_SOCKET:
        print("找不到 docker.sock，请确认 Docker Desktop 已启动")
        sys.exit(1)
    print("使用 socket: %s" % DOCKER_SOCKET)
    print("面板地址:   http://localhost:%d" % PORT)
    print("按 Ctrl+C 退出\n")
    ThreadedServer(('127.0.0.1', PORT), Handler).serve_forever()
