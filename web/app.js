const $ = (s) => document.querySelector(s);
const csrf = $('meta[name="csrf-token"]').content;
let state, page = 'home', tool = null, search = '', localItems = [], localError = '';
let settingsDirty = false, fetching = false, toolBusy = false;
let appearance={source:'system',dark:matchMedia('(prefers-color-scheme: dark)').matches};
function applyAppearance(value) {
  appearance=value;document.documentElement.dataset.theme=value.dark?'dark':'light';
  $('#theme-select').value=value.source;
  document.querySelectorAll('[data-theme]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.theme===value.source)));
}
async function chooseAppearance(source) {
  if(window.workspace?.setAppearance)applyAppearance(await window.workspace.setAppearance(source));
  else applyAppearance({source,dark:source==='dark'||source==='system'&&matchMedia('(prefers-color-scheme: dark)').matches});
}
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = { queued:'待归档',archiving:'归档中',archived:'已归档 PDF',linked_archived:'已关联同步 PDF',metadata_archived:'文献已归档',existing:'已关联已有文献',review:'疑似重复',error:'待重试',pdf_pending:'部分完成，待重试',local_pending:'等待 Zotero 同步',unsupported:'需手动处理'};
const goodStatuses = ['archived','linked_archived','metadata_archived','existing'];
const fmtTime = value => value ? new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '尚未运行';
async function api(path,body) {
  const options = body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)};
  const response = await fetch(path,options);
  const data = await response.json();
  if(!response.ok)throw new Error(data.error || '操作失败');
  return data;
}
function toast(message,error=false) {
  const el=$('#toast');el.textContent=message;el.classList.toggle('error',error);el.classList.remove('hidden');
  clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),5500);
}
async function refresh() {
  if(fetching)return;
  fetching=true;
  try { state=await api('/api/status'); updateChrome(); if(!tool && page!=='designer' && !(page==='settings' && settingsDirty)) render(); }
  catch(error){if(!state)$('#main').innerHTML=`<div class="error-banner">${esc(error.message)}</div>`;}
  finally{fetching=false;}
}
function updateChrome() {
  const c=state.counts;
  $('#queue-count').textContent=state.jobs.length;
  $('#sync-button').disabled=state.busy;
  $('#sync-button').textContent=state.busy ? '正在处理…' : '立即归档';
  $('#sync-indicator').textContent=state.busy?'正在检查与归档':state.auto_sync_running?'自动归档已开启':state.missing.length?'等待账户连接':'自动归档已暂停';
  $('#sync-indicator').classList.toggle('connected',state.auto_sync_running);
}
function navigate(name) {
  if(page==='designer'&&name!=='designer')window.NexusDesigner?.unmount();
  page=name;tool=null;settingsDirty=false;
  document.body.classList.toggle('designer-open',name==='designer');
  document.body.classList.remove('tool-open');$('#tool-controls').classList.add('hidden');
  window.workspace?.hideTool();
  $('.nav.active')?.classList.remove('active');$(`.nav[data-page="${name}"]`)?.classList.add('active');
  $('#page-title').textContent={home:'工作台',designer:'系统设计器',archive:'归档记录',library:'本地文献',settings:'连接与设置'}[name];
  render();if(name==='library')loadLibrary();
}
function hero(title,description,badge='YOUR RESEARCH SPACE') {
  return `<div class="hero"><div><div class="eyebrow">RESEARCH, CONNECTED.</div><h1>${title}</h1><p>${description}</p></div><span class="hero-badge">${badge}</span></div>`;
}
function serviceStatus(letter,kind,name,detail,ready) {
  return `<div class="status-row"><span class="service-letter ${kind}-letter">${letter}</span><div><b>${name}</b><small>${detail}</small></div><span class="status-tag ${ready?'good':''}">${ready?'已就绪':'待连接'}</span></div>`;
}
function home() {
  const counts=state.counts, completed=state.jobs.filter(j=>goodStatuses.includes(j.status)).length;
  const pending=state.jobs.filter(j=>['error','pdf_pending','review','unsupported','local_pending'].includes(j.status)).length;
  const connected=state.missing.length===0;
  const steps=[
    ['连接你的账户','填写 alphaXiv 与 Zotero 的专用 API Key。',connected,'settings','连接账户'],
    ['选择收藏文件夹','读取收藏；未指定时处理全部返回的文件夹。',state.folders.length>0,'settings','选择文件夹'],
    ['开启自动归档','去重后保存文献与 PDF；可查看每条处理结果。',state.auto_sync_running,'settings','设置归档']
  ];
  const cadence=state.config.sync_interval_seconds===86400?'每天':state.config.sync_interval_seconds%3600===0?'每 '+state.config.sync_interval_seconds/3600+' 小时':'每 '+Math.round(state.config.sync_interval_seconds/60)+' 分钟';
  return hero('研究，从这里继续。','发现值得读的论文，连接已有知识，推进下一个研究问题。')+
    `<div class="section-label">你的研究工具</div><div class="launch-grid">${[['alpha','α','alpha','alphaXiv','发现论文 · 收藏与阅读'],['zotero','Z','zotero','Zotero','文献归档 · 批注与引用'],['openresearch','◩','orx','OpenResearch','研究对话 · 实验与探索']].map(([name,letter,kind,title,description])=>`<button class="launch-card" data-tool="${name}"><span class="service-letter ${kind}-letter">${letter}</span><span><b>${title}</b><small>${description}</small></span><span class="launch-arrow">↗</span></button>`).join('')}</div>`+
    `<div class="metrics">${[['收藏候选',state.jobs.length,'已进入归档队列'],['完成归档',completed,'文献与 PDF 已关联'],['待处理',pending,'需要留意的归档任务'],['自动检查',state.auto_sync_running?cadence:'未开启','最近：'+fmtTime(state.last_sync?.time)]].map(([l,v,s])=>`<div class="metric"><div class="metric-label">${l}</div><div class="metric-value">${v}</div><small>${s}</small></div>`).join('')}</div>`+
    (state.last_error?.message?`<div class="error-banner">${esc(state.last_error.message)}</div>`:'')+
    `<div class="content-grid"><div><section class="panel"><div class="panel-head"><h2>${connected?'你的归档流程':'开始连接研究流程'}</h2><small>收藏 → 去重 → 归档</small></div>
    <div class="workflow"><div class="workflow-step"><span class="workflow-icon alpha-letter">α</span><b>alphaXiv</b><small>发现与收藏</small></div><span class="workflow-arrow">→</span><div class="workflow-step"><span class="workflow-icon"><img class="nexus-mark" src="/icon.png" alt=""></span><b>Research Nexus</b><small>去重与自动归档</small></div><span class="workflow-arrow">→</span><div class="workflow-step"><span class="workflow-icon zotero-letter">Z</span><b>Zotero</b><small>文献与 PDF 归档</small></div></div>
    ${(!connected?steps:steps.slice(2)).map(([title,detail,done,target,action],i)=>`<div class="onboard-row"><span class="step-number ${done?'done':''}">${done?'✓':String(i+1).padStart(2,'0')}</span><div class="onboard-text"><b>${title}</b><p>${detail}</p></div><button class="button small" data-go="${target}">${done?'设置':action}</button></div>`).join('')}</section>
    <section class="panel"><div class="panel-head"><h2>最近归档</h2><button class="button small" data-go="archive">全部记录 →</button></div>${state.jobs.length?paperTable(state.jobs.slice(0,4)):empty('你的第一篇归档论文，将出现在这里。','连接账户后，收藏会在下一次检查时进入队列。')}</section></div>
    <div><section class="panel"><div class="panel-head"><h2>工具连接</h2><small>LOCAL WORKSPACE</small></div><div class="panel-body">${serviceStatus('α','alpha','alphaXiv',state.checks?.alpha?.ok?'收藏读取已连接':state.config.alphaxiv_key_configured?'已配置 Key，待检查连接':'需要 API Key 读取收藏',state.checks?.alpha?.ok)}${serviceStatus('Z','zotero','Zotero',state.config.zotero_key_configured?'已配置 Key，桌面端请保持同步':'桌面版 9.0.3 · 归档使用 Web API',state.checks?.zotero_web?.ok)}${serviceStatus('O','orx','OpenResearch',state.openresearch_installed?'本地应用已安装 · 点击侧边栏接入':'尚未指定本地程序',state.openresearch_installed)}<div class="note">Zotero 与 OpenResearch 使用本机应用窗口；alphaXiv 保留网页阅读界面。</div></div></section>
    <section class="panel"><div class="panel-head"><h2>活动记录</h2><small>${state.busy?'处理中':'最近操作'}</small></div><div class="panel-body">${state.events.length?state.events.slice(0,5).map(e=>`<div class="event ${esc(e.level)}"><span class="event-dot"></span><div>${esc(e.message)}<small>${fmtTime(e.time)}</small></div></div>`).join(''):'<div class="subtle">还没有归档活动。完成连接后，处理过程会记录在这里。</div>'}</div></section></div></div>`;
}
function empty(title,description='') {return `<div class="empty"><div class="empty-symbol">▤</div>${title}<p>${description}</p></div>`;}
function paperTable(jobs) {
  return `<table class="table"><thead><tr><th>论文</th><th>归档状态</th><th>操作</th></tr></thead><tbody>${jobs.map(j=>`<tr><td><div class="paper-title">${esc(j.paper.title||j.canonical)}</div><div class="paper-meta">${esc(j.paper.arxiv+j.paper.version)} · ${esc(j.paper.folder_names.join(' / '))}</div>${j.error?`<div class="paper-error">${esc(j.error)}</div>`:''}${j.status==='review'?`<div class="row-actions">${j.candidates.map(c=>`<button class="button small" data-link-job="${j.id}" data-key="${esc(c.key)}" title="${esc(c.title)}">关联 ${esc(c.key)}</button>`).join('')}<button class="button small" data-separate-job="${j.id}">作为独立文献归档</button></div>`:''}</td><td><span class="status-tag ${goodStatuses.includes(j.status)?'good':['review','error','pdf_pending','unsupported'].includes(j.status)?'warn':''}">${labels[j.status]||esc(j.status)}</span></td><td><div class="row-actions"><button class="button small" data-paper="${esc(j.paper.source_url)}">论文</button>${j.pdf_path?`<button class="button small" data-pdf="${j.id}">PDF</button>`:''}${j.item_key?`<button class="button small" data-zotero-key="${esc(j.item_key)}">条目</button>`:''}</div></td></tr>`).join('')}</tbody></table>`;
}
function archive() {
  const jobs=state.jobs.filter(j=>`${j.paper.title} ${j.canonical} ${j.paper.folder_names.join(' ')}`.toLowerCase().includes(search.toLowerCase()));
  return hero('归档记录','每篇论文都有明确的处理结果。失败后重试会核对已有条目，保留原编号。','ARCHIVE')+
    `<div class="toolbar"><input id="archive-search" class="search" placeholder="搜索标题、arXiv ID 或文件夹" value="${esc(search)}"><span class="filter-label">当前文献库 · ${jobs.length} 篇</span></div>`+
    state.warnings.map(w=>`<div class="note warning">${esc(w)}</div>`).join('')+
    `<section class="panel">${jobs.length?paperTable(jobs):empty('暂无归档记录','在 alphaXiv 收藏论文后，点击“立即归档”。')}</section>`;
}
function settings() {
  const c=state.config;
  return hero('让工作空间，适合你。','管理界面外观、账户连接与自动归档。','PREFERENCES')+
    `<section class="panel"><div class="panel-head"><h2>外观</h2><small>立即生效 · 自动保存</small></div><div class="panel-body"><div class="theme-choices">${[['light','浅色'],['dark','深色'],['system','跟随系统']].map(([value,label])=>`<button type="button" class="theme-choice" data-theme="${value}" aria-pressed="${appearance.source===value}"><span class="theme-swatch swatch-${value}"></span>${label}</button>`).join('')}</div><p class="appearance-description">调整 Research Nexus 工作台外观。本地工具使用各自的主题设置。</p><div class="design-reference"><b>设计风格参考：OpenAI Codex 桌面端</b><p>按本机 Windows 版的字体族、字号层级、字重和行高调整：Segoe UI · 正文 14px · 控件 13px · 辅助文字 12px。</p></div></div></section>`+
    `<form id="settings-form"><div class="settings-grid"><section class="panel"><div class="panel-head"><h2>01 / alphaXiv</h2><span class="status-tag ${c.alphaxiv_key_configured?'good':''}">${c.alphaxiv_key_configured?'已保存密钥':'待授权'}</span></div><div class="panel-body"><div class="field"><label for="alpha-key">API Key</label><input id="alpha-key" name="alphaxiv_key" type="password" autocomplete="new-password" placeholder="${c.alphaxiv_key_configured?'已保存 · 留空保留现有密钥':'在 alphaXiv Settings → API Keys 创建'}"><small>只读取所选收藏。<button type="button" class="button small" data-tool="alpha">在工作台打开 alphaXiv</button></small></div><div class="form-top"><h3>收藏文件夹</h3><button class="button small" type="button" id="preview-button">读取收藏</button></div><div id="folder-list">${state.folders.length?state.folders.map(f=>`<label class="folder-row"><input type="checkbox" name="alpha_folder_ids" value="${esc(f.id)}" ${c.alpha_folder_ids.includes(f.id)?'checked':''}>${esc(f.name)}<small>${f.returned}/${f.paper_count}${f.partial?' · 部分返回':''}</small></label>`).join(''):'<div class="subtle">先保存 alphaXiv Key，再读取文件夹。</div>'}</div><p class="subtle">未勾选表示处理全部返回的文件夹。接口若截断会提示。</p></div></section>
    <section class="panel"><div class="panel-head"><h2>02 / Zotero</h2><span class="status-tag ${c.zotero_key_configured?'good':''}">${c.zotero_key_configured?'已保存密钥':'待授权'}</span></div><div class="panel-body"><div class="field"><label for="zotero-id">数字 User ID</label><input id="zotero-id" name="zotero_user_id" inputmode="numeric" value="${esc(c.zotero_user_id)}" placeholder="可在 Zotero API Keys 页面查看"><small>个人库数字 ID，与用户名不同。</small></div><div class="field"><label for="zotero-key">API Key</label><input id="zotero-key" name="zotero_key" type="password" autocomplete="new-password" placeholder="${c.zotero_key_configured?'已保存 · 留空保留现有密钥':'需要个人库读写及文件权限'}"><small><button class="button small" type="button" data-zotero-settings>管理 API 密钥（网站）</button> 已有桌面文献请先同步到 Zotero 账户。</small></div><div class="field"><label for="collection">目标顶层分类</label><input id="collection" name="zotero_collection" value="${esc(c.zotero_collection)}"><small>首次归档时创建；已有条目仅加入分类，不覆盖人工元数据。</small></div></div></section>
    <section class="panel"><div class="panel-head"><h2>03 / 自动归档</h2><small>工作台运行时生效</small></div><div class="panel-body"><label class="toggle-label"><input name="auto_sync" type="checkbox" ${c.auto_sync?'checked':''}>启用自动检查与归档</label><label class="toggle-label"><input name="download_pdf" type="checkbox" ${c.download_pdf?'checked':''}>下载经过文件类型验证的 arXiv PDF</label><div class="field"><label for="pdf-storage">PDF 保存方式</label><select id="pdf-storage" name="pdf_storage"><option value="zotero" ${c.pdf_storage==='zotero'?'selected':''}>Zotero 云附件</option><option value="linked_folder" ${c.pdf_storage==='linked_folder'?'selected':''}>Google Drive / 同步文件夹链接</option></select></div><div class="field"><label for="linked-pdf-dir">PDF 同步文件夹</label><input id="linked-pdf-dir" name="linked_pdf_dir" value="${esc(c.linked_pdf_dir||'')}" placeholder="选择 Google Drive 内已有的论文文件夹"><button class="button small" type="button" id="choose-pdf-folder">选择文件夹</button><small>只保存 PDF。文件需由 Google Drive 桌面版同步；Zotero 桌面可阅读和批注，手机 App 不支持这类文件链接。</small></div><label class="toggle-label"><input name="upload_pdf" type="checkbox" ${c.upload_pdf?'checked':''}>Zotero 云附件模式下上传 PDF</label><div class="field"><label>检查间隔（秒）</label><input name="sync_interval_seconds" type="number" min="60" max="86400" value="${c.sync_interval_seconds}"></div><div class="field"><label>每轮最多处理论文数</label><input name="max_papers_per_sync" type="number" min="1" max="200" value="${c.max_papers_per_sync}"></div></div></section>
    <section class="panel"><div class="panel-head"><h2>04 / OpenResearch 本地应用</h2><span class="status-tag good">桌面应用</span></div><div class="panel-body"><p>打开此电脑已安装的 OpenResearch，继续现有研究项目。</p><button class="button" type="button" data-tool="openresearch">打开 OpenResearch</button><div class="note">模型与 Agent 授权在本地 OpenResearch 内完成。关闭工作台窗口后，研究应用继续后台运行。</div></div></section></div><div class="settings-footer"><button type="submit" class="button primary">保存设置</button><button type="button" class="button" id="check-button">检查连接</button><small>保存后密钥输入框会清空，已保存的密钥继续保留。</small></div></form>`+
    (state.checks?`<section class="panel"><div class="panel-head"><h2>最近连接检查</h2><small>${fmtTime(state.checks.time)}</small></div><div class="panel-body">${['alpha','zotero_web'].map(k=>state.checks[k]?`<p class="subtle">${k==='alpha'?'alphaXiv':'Zotero Web'}：${esc(state.checks[k].message)}</p>`:'').join('')}<p class="subtle">Zotero 本地读取：${state.checks.zotero_local?.online?'可用':'未连接'}</p></div></section>`:'');
}
function library() {
  return hero('你的本地文献','通过 Zotero 本地只读接口查看已有文献；完整的引用与批注功能可在 Zotero 中使用。','LIBRARY')+
    `<div class="toolbar"><input id="library-search" class="search" placeholder="按标题、作者搜索本地文献" value="${esc(search)}"><button class="button" id="library-load">搜索 / 刷新</button><button class="button" id="launch-zotero">启动 Zotero</button><button class="button" data-tool="zotero">打开桌面版</button></div>`+
    (localError?`<div class="note warning">${esc(localError)}</div>`:'')+
    `<section class="panel">${localItems.length?`<table class="table"><thead><tr><th>论文</th><th>作者</th><th>日期</th><th>查看</th></tr></thead><tbody>${localItems.map(i=>`<tr><td><div class="paper-title">${esc(i.title)}</div><span class="paper-meta">${esc(i.key)}</span></td><td>${esc(i.authors)}</td><td>${esc(i.date)}</td><td><button class="button small" data-zotero-key="${esc(i.key)}">桌面条目</button></td></tr>`).join('')}</tbody></table>`:empty('本地文献列表','启动 Zotero 并允许本地通信后，点击刷新。')}</section><p class="subtle">每次最多显示 100 条；可通过搜索缩小范围。</p>`;
}
function render() {
  if(page==='designer'){window.NexusDesigner?.mount($('#main'),{api,toast,openBuiltin:openTool});return;}
  if(!state)return;
  $('#main').innerHTML=({home,archive,settings,library}[page]||home)();
}
async function loadLibrary() {
  try {localItems=await api('/api/local-library?q='+encodeURIComponent(search));localError='';}
  catch(e){localError=e.message;localItems=[];}if(page==='library')render();
}
async function openTool(name,url) {
  if(!window.workspace) {toast('请通过 Research Nexus 桌面启动器打开，才能在同一窗口使用工具。',true);return;}
  window.NexusDesigner?.unmount();document.body.classList.remove('designer-open');
  const native=['zotero','openresearch'].includes(name);
  tool=name;document.body.classList.add('tool-open');$('#tool-controls').classList.remove('hidden');
  $('#tool-window').classList.toggle('hidden',!native);
  $('#tool-back').classList.toggle('hidden',native);$('#tool-reload').classList.toggle('hidden',native);
  $('.nav.active')?.classList.remove('active');$(`.nav[data-tool="${name}"]`)?.classList.add('active');
  $('#page-title').textContent={alpha:'alphaXiv',zotero:'Zotero',openresearch:'OpenResearch',pdf:'PDF'}[name];
  if(native) {
    $('#tool-address').textContent='本地应用 · 嵌入工作台';
    $('#main').innerHTML=`<div class="tool-placeholder"><h2>正在打开 ${name==='zotero'?'Zotero':'OpenResearch'}…</h2></div>`;
    try {await window.workspace.showNativeTool(name,name==='zotero'&&typeof url==='string'?url:undefined);}
    catch(e){toast(e.message,true);navigate('home');}
    return;
  }
  $('#tool-address').textContent=url||'正在恢复上次阅读…';
  try {
    const current=await window.workspace.showTool(name,url);
    if(tool===name)$('#tool-address').textContent=(current.loading?'正在加载 · ':'')+(current.url||'');
  }catch(e){toast(e.message,true);navigate('home');}
}
document.addEventListener('click',async event=>{
  const b=event.target.closest('button');if(!b)return;
  try {
    if(b.dataset.theme)await chooseAppearance(b.dataset.theme);
    else if(b.id.startsWith('window-'))await window.workspace?.windowAction(b.id.slice(7));
    else if(b.dataset.page||b.dataset.go)navigate(b.dataset.page||b.dataset.go);
    else if(b.dataset.tool)await openTool(b.dataset.tool);
    else if(b.hasAttribute('data-zotero-settings'))await window.workspace?.zoteroAccountSettings();
    else if(b.dataset.paper)await openTool('alpha',b.dataset.paper);
    else if(b.dataset.pdf)await openTool('pdf',location.origin+'/api/pdf/'+b.dataset.pdf);
    else if(b.dataset.zoteroKey)await openTool('zotero',b.dataset.zoteroKey);
    else if(b.id==='sync-button') {await api('/api/sync',{});toast('归档已开始，可在记录中查看进度。');await refresh();}
    else if(b.id==='preview-button') {if(settingsDirty)throw new Error('请先保存刚输入的设置，再读取收藏。');await api('/api/preview',{});toast('正在读取收藏；请稍等。');await refresh();}
    else if(b.id==='check-button'){if(settingsDirty)throw new Error('请先保存刚输入的设置，再检查连接。');await api('/api/connections',{});toast('正在检查连接，不会写入测试文献。');await refresh();}
    else if(b.id==='choose-pdf-folder'){
      const folder=await window.workspace?.choosePdfFolder();
      if(folder){$('#linked-pdf-dir').value=folder;settingsDirty=true;}
    }
    else if(b.id==='library-load')await loadLibrary();
    else if(b.id==='launch-zotero')await openTool('zotero');
    else if(b.id==='tool-back')await window.workspace?.navigate('back');
    else if(b.id==='tool-reload')await window.workspace?.navigate('reload');
    else if(b.id==='tool-fullscreen')await window.workspace?.toggleFullscreen();
    else if(b.id==='tool-window')await window.workspace?.releaseNativeTool();
    else if(b.dataset.linkJob||b.dataset.separateJob){await api('/api/resolve',{job_id:Number(b.dataset.linkJob||b.dataset.separateJob),action:b.dataset.linkJob?'link':'separate',item_key:b.dataset.key});toast('已保存；下一轮归档会应用。');await refresh();}
  }catch(e){toast(e.message,true);}
});
document.addEventListener('input',event=>{
  if(event.target.closest('#settings-form'))settingsDirty=true;
  if(event.target.id==='archive-search') {search=event.target.value;const pos=event.target.selectionStart;render();$('#archive-search').focus();$('#archive-search').setSelectionRange(pos,pos);}
  if(event.target.id==='library-search')search=event.target.value;
});
$('#theme-select').addEventListener('change',event=>chooseAppearance(event.target.value).catch(e=>toast(e.message,true)));
document.addEventListener('submit',async event=>{
  if(event.target.id!=='settings-form')return;event.preventDefault();
  const data=new FormData(event.target),payload=Object.fromEntries(data);
  payload.alpha_folder_ids=data.getAll('alpha_folder_ids');
  for(const k of ['auto_sync','download_pdf','upload_pdf'])payload[k]=data.has(k);
  for(const k of ['sync_interval_seconds','max_papers_per_sync'])payload[k]=Number(payload[k]);
  try{await api('/api/config',payload);settingsDirty=false;toast('设置已保存。');await refresh();}catch(e){toast(e.message,true);}
});
window.workspace?.onToolState(data=>{if(tool===data.tool){$('#tool-address').textContent=(data.loading?'正在加载 · ':'')+(data.url||'');if(data.error)toast(data.error,true);}});
window.workspace?.onOpenDesigner?.(()=>navigate('designer'));
window.addEventListener('nexus-custom-tool',event=>{
  const data=event.detail;window.NexusDesigner?.unmount();document.body.classList.remove('designer-open');
  tool=data.tool;document.body.classList.add('tool-open');$('#tool-controls').classList.remove('hidden');
  $('#tool-window').classList.add('hidden');$('#tool-back').classList.remove('hidden');$('#tool-reload').classList.remove('hidden');
  $('.nav.active')?.classList.remove('active');$('#page-title').textContent=data.name;$('#tool-address').textContent=data.url||'';
});
window.workspace?.onFullscreenState(value=>document.body.classList.toggle('workspace-fullscreen',value));
window.workspace?.onNativeToolState(data=>{
  if(data.event==='error') {toast(data.message,true);if(tool===data.tool)navigate('home');return;}
  if(data.event==='activate') {
    tool=data.tool;document.body.classList.add('tool-open');$('#tool-controls').classList.remove('hidden');
    $('#tool-window').classList.remove('hidden');$('#tool-back').classList.add('hidden');$('#tool-reload').classList.add('hidden');
    $('#tool-address').textContent='本地应用 · 嵌入工作台';$('#page-title').textContent=tool==='zotero'?'Zotero 桌面版':'OpenResearch';
    $('.nav.active')?.classList.remove('active');$(`.nav[data-tool="${tool}"]`)?.classList.add('active');
    $('#main').innerHTML='';
  } else if(['released','closed'].includes(data.event)&&tool===data.tool) {
    $('#main').innerHTML=`<div class="tool-placeholder"><h2>本地应用${data.event==='released'?'已弹出为独立窗口':'已关闭'}</h2><button class="button" data-tool="${tool}">在工作台中打开</button></div>`;
  }
});
window.workspace?.getState().then(current=>{
  document.body.classList.toggle('workspace-fullscreen',current.fullscreen);
  if(current.tool?.startsWith('custom-'))window.dispatchEvent(new CustomEvent('nexus-custom-tool',{detail:current}));
  else if(current.tool)openTool(current.tool,current.url);
}).catch(()=>{});
window.workspace?.onAppearance?.(applyAppearance);
if(window.workspace?.getAppearance)window.workspace.getAppearance().then(applyAppearance).catch(()=>{});
refresh();setInterval(refresh,4000);
