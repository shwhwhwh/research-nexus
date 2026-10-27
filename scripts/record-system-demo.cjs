// Real RN + real archive engine, isolated fake services. Captures own webContents only.
const {app,BrowserWindow,ipcMain,nativeTheme}=require('electron');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const root=path.resolve(__dirname,'..'),testOnly=process.argv.includes('--test-only');
const runRoot=path.join(root,'artifacts','system-demo-'+Date.now()),assets=path.join(root,'docs','assets');
fs.mkdirSync(path.join(runRoot,'web'),{recursive:true});fs.mkdirSync(assets,{recursive:true});
for(const name of ['index.html','app.js','appearance.js','style.css','systems.js','systems.css','designer.js','designer.css','icon.png','icon.svg'])fs.copyFileSync(path.join(root,'web',name),path.join(runRoot,'web',name));
app.setPath('userData',path.join(runRoot,'profile'));app.on('window-all-closed',()=>{});nativeTheme.themeSource='light';
let backend,win,address,csrf,encoder,encoderExit,frames=0,exeChoice=0,encoderError='';const checkpoints=[];
const delay=ms=>new Promise(ok=>setTimeout(ok,ms));
async function until(fn,message,timeout=20000){const start=Date.now();while(Date.now()-start<timeout){if(await fn())return;await delay(90);}throw Error(message);}
async function api(route,payload){const r=await fetch(address+route,payload===undefined?{}:{method:'POST',headers:{Origin:address,'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error||route);return data;}
async function cleanup(){if(encoder&&!encoder.stdin.destroyed)encoder.stdin.end();if(address&&csrf)await api('/api/shutdown',{}).catch(()=>{});if(win&&!win.isDestroyed())win.destroy();if(backend&&backend.exitCode===null)await Promise.race([once(backend,'exit'),delay(2500)]);if(backend&&backend.exitCode===null)backend.kill();}
app.whenReady().then(async()=>{
  let runtime={};try{runtime=JSON.parse(fs.readFileSync(path.join(root,'runtime.local.json'),'utf8'));}catch{}
  const env={...process.env};for(const name of Object.keys(env))if(/ALPHAXIV|ZOTERO|RESEARCH_BRIDGE|RN_.*(?:KEY|TOKEN)/.test(name))delete env[name];
  backend=spawn(process.env.RESEARCH_NEXUS_PYTHON||runtime.python||'python',['-u','-m','bridge.demo_system','--root',runRoot],{cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
  backend.stderr.on('data',chunk=>fs.appendFileSync(path.join(runRoot,'backend.log'),chunk));
  address=await new Promise((resolve,reject)=>{let buffer='';backend.stdout.on('data',chunk=>{buffer+=chunk;for(const line of buffer.split('\n'))try{const m=JSON.parse(line);if(m.ready)resolve(m.url);}catch{}});backend.on('error',reject);backend.on('exit',code=>reject(Error('Demo backend exited '+code)));setTimeout(()=>reject(Error('Backend timeout')),15000).unref();});
  csrf=(await fetch(address).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)[1];
  ipcMain.handle('workspace-state',()=>({tool:null,fullscreen:false}));ipcMain.handle('hide-tool',()=>{});
  ipcMain.handle('appearance-get',()=>({source:nativeTheme.themeSource,dark:nativeTheme.shouldUseDarkColors}));
  ipcMain.handle('appearance-set',(_e,source)=>{nativeTheme.themeSource=source;return{source,dark:nativeTheme.shouldUseDarkColors};});
  ipcMain.handle('choose-tool-executable',()=>path.join(runRoot,'demo-programs',exeChoice++%2?'OpenResearch.exe':'zotero.exe'));
  ipcMain.handle('choose-pdf-folder',()=>path.join(runRoot,'demo-drive','Research PDFs'));
  const exported=path.join(runRoot,'downloaded-template.rn-system.json');
  ipcMain.handle('save-system-template',()=>{fs.copyFileSync(path.join(root,'system-templates','literature-workspace.rn-system.json'),exported);return true;});
  ipcMain.handle('choose-system-template',()=>JSON.parse(fs.readFileSync(exported,'utf8')));
  ipcMain.handle('open-setup-link',()=>true);ipcMain.handle('zotero-account-settings',()=>true);
  win=new BrowserWindow({show:false,width:1440,height:1000,useContentSize:true,webPreferences:{preload:path.join(root,'desktop','preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,offscreen:testOnly,backgroundThrottling:false}});
  const wc=win.webContents,blocked=[];
  wc.session.webRequest.onBeforeRequest((details,callback)=>{const allowed=details.url.startsWith(address+'/')||details.url.startsWith('data:');if(!allowed)blocked.push(new URL(details.url).origin);callback({cancel:!allowed});});
  nativeTheme.on('updated',()=>wc.send('appearance-state',{source:nativeTheme.themeSource,dark:nativeTheme.shouldUseDarkColors}));
  async function showSurface(tool){
    const state=await api('/api/status');const titles=state.jobs.map(j=>j.paper.title);const samples=['Fictional demo: Tiny robots','Fictional demo: Learning agents'];let title,description,rows;
    if(tool==='alpha'){title='alphaXiv · 演示收藏';description='模拟服务 · 两篇虚构论文 · 未登录任何真实账号';rows=samples.map(t=>({title:t,detail:'已收藏 · Demo collection'}));}
    else if(tool==='zotero'){title='Zotero · 归档结果预览';description='模拟服务 · 以下记录由真实 RN 归档引擎生成';rows=titles.map(t=>({title:t,detail:'文献条目 + 来源笔记 + Google Drive PDF 链接'}));}
    else {title='OpenResearch · 继续研究';description='示意界面 · 论文交接为人工操作';rows=[{title:'选择已归档论文的链接 / PDF',detail:'在研究对话中提供所选文献，使用自己的 Agent 登录。'},{title:'下一步：阅读、形成假设、安排实验',detail:'本演示不生成或展示真实研究对话。'}];}
    await wc.executeJavaScript(`(()=>{document.querySelector('#main').innerHTML='<section class="demo-service"><div class="eyebrow">SIMULATED SERVICE · NO PERSONAL ACCOUNT</div><h1></h1><p></p><div class="demo-rows"></div></section>';document.querySelector('.demo-service h1').textContent=${JSON.stringify(title)};document.querySelector('.demo-service>p').textContent=${JSON.stringify(description)};for(const row of ${JSON.stringify(rows)}){const card=document.createElement('article');const b=document.createElement('b');b.textContent=row.title;const p=document.createElement('p');p.textContent=row.detail;card.append(b,p);document.querySelector('.demo-rows').append(card);}})()`);
    return{native:tool!=='alpha',url:'模拟服务 · 虚构数据',loading:false};
  }
  ipcMain.handle('show-tool',(_e,{tool})=>showSurface(tool));ipcMain.handle('show-native-tool',(_e,{tool})=>showSurface(tool));
  await win.loadURL(address);await until(()=>wc.executeJavaScript('!!document.querySelector(".hero h1")'),'RN dashboard not ready');
  await wc.insertCSS(`*{transition:none!important;animation:none!important}.window-controls{display:none!important}.top-actions{margin-right:15px}.demo-service{padding:35px 32px}.demo-service h1{font-size:28px;font-weight:590}.demo-service>p,.demo-rows p{color:var(--muted);font-size:14px;line-height:23px}.demo-rows{display:grid;gap:18px;max-width:800px;margin-top:32px}.demo-rows article{border:1px solid var(--border);border-radius:12px;padding:24px;background:var(--surface)}body #main{padding-bottom:125px}#demo-caption{position:fixed;bottom:0;left:236px;right:0;background:var(--surface);border-top:1px solid var(--border);z-index:9998;padding:15px 26px;height:88px;box-sizing:border-box;font:510 17px/26px "Segoe UI",sans-serif;color:var(--ink)}#demo-caption small{display:block;font-size:13px;font-weight:400;color:var(--muted)}#demo-badge{position:fixed;left:246px;top:12px;z-index:9997;font:11px/20px "Segoe UI",sans-serif;color:var(--muted);padding:4px 8px;background:var(--bg)}.breadcrumb{visibility:hidden}#demo-cursor{position:fixed;width:16px;height:16px;border:2px solid #8294d7;background:#96a5ef44;border-radius:50%;z-index:9999;pointer-events:none;transform:translate(-50%,-50%)}`);
  await wc.executeJavaScript(`document.querySelector('[data-page=systems]').click();document.body.insertAdjacentHTML('beforeend','<div id="demo-caption"></div><div id="demo-badge">ISOLATED DEMO · SIMULATED SERVICES · FICTIONAL DATA</div><div id="demo-cursor"></div>')`);
  await until(()=>wc.executeJavaScript('!!document.querySelector(".system-banner")'),'System Template not rendered');
  for(let n=0;n<6;n++){await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});await delay(150);}
  if(!testOnly){encoder=spawn(process.env.RN_DEMO_FFMPEG||'ffmpeg',['-y','-hide_banner','-loglevel','error','-f','image2pipe','-vcodec','mjpeg','-framerate','12','-i','pipe:0','-an','-c:v','libx264','-preset','medium','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',path.join(assets,'research-nexus-system-demo.mp4')],{windowsHide:true,stdio:['pipe','ignore','pipe']});encoder.stderr.on('data',d=>encoderError+=d);encoder.stdin.on('error',()=>{});encoderExit=once(encoder,'exit');}
  async function frame(){if(testOnly)return;await delay(1000/12);if(encoder.exitCode!==null)throw Error(encoderError);const shot=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});if(!encoder.stdin.write(shot.toJPEG(90)))await once(encoder.stdin,'drain');frames++;}
  async function hold(seconds){if(testOnly){await delay(80);return;}for(let n=0;n<Math.round(seconds*12);n++)await frame();}
  async function caption(en,zh){await wc.executeJavaScript(`(()=>{const el=document.querySelector('#demo-caption');el.replaceChildren(Object.assign(document.createElement('span'),{textContent:${JSON.stringify(en)}}),Object.assign(document.createElement('small'),{textContent:${JSON.stringify(zh)}}));})()`);checkpoints.push({seconds:frames/12,en,zh});}
  async function click(selector){await wc.executeJavaScript(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'center'})`);await delay(100);const point=await wc.executeJavaScript(`(()=>{const b=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return{x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)}})()`);await wc.executeJavaScript(`(()=>{const el=document.querySelector('#demo-cursor');el.style.left='${point.x}px';el.style.top='${point.y}px';})()`);await hold(.25);wc.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...point});wc.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...point});await delay(200);}
  async function value(selector,text){await wc.executeJavaScript(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(text)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
  async function shot(name){await hold(.3);const image=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});fs.writeFileSync(path.join(runRoot,name+'.png'),image.toPNG());}
  await caption('System Template 01. One workspace for your research.','第一个模板：alphaXiv / Zotero / OpenResearch + Google Drive。');await hold(3);await shot('01-overview');
  assert.equal((await api('/api/systems')).installed,false);
  await caption('Download the template, then import it into RN.','模板不包含账号或文献；下载后可在 RN 中导入。');
  await click('[data-system=download]');assert(fs.existsSync(exported));await hold(1);await click('[data-system=import]');
  await until(()=>wc.executeJavaScript('!!document.querySelector("#system-setup-form")'),'Template import failed');
  assert.equal((await api('/api/systems')).installed,true);assert.equal((await api('/api/systems')).enabled,false);
  await caption('Set up your own API keys and local applications.','这里只使用虚构授权；真实用户填写自己的 Key 并选择安装路径。');
  await value('[name=alphaxiv_key]','demo-alpha-key-not-real');await value('[name=zotero_key]','demo-zotero-key-not-real');await value('[name=zotero_user_id]','123');await hold(1.8);
  await click('[data-system-pick=zotero_exe]');await click('[data-system-pick=openresearch_exe]');await click('[name=zotero_sync_enabled]');await click('[name=orx_agent_ready]');await hold(1.5);
  await caption('Sign in to Drive for desktop and select its PDF folder.','真实登录在 Drive 桌面端完成；RN 保存 PDF，客户端负责同步。');
  await click('[data-system=folder]');await click('[name=drive_signed_in]');await hold(2);await click('#system-setup-form button[type=submit]');
  await until(()=>wc.executeJavaScript('document.querySelector("[name=alphaxiv_key]").value===""'),'Configuration not saved');
  await click('[data-system=check]');await until(async()=>Boolean((await api('/api/systems')).ready),'Setup requirements not satisfied');
  await until(()=>wc.executeJavaScript('!document.querySelector("[data-system=enable]").disabled'),'Enable button not ready');
  await caption('Reviewed system. Ready for daily bookmark checks.','完成授权和软件配置后启用系统，每天检查一次收藏。');await hold(2);await shot('02-ready');
  await click('[data-system=enable]');await until(async()=>Boolean((await api('/api/systems')).enabled),'System not enabled');
  const enabled=await api('/api/status');assert.equal(enabled.config.sync_interval_seconds,86400);assert.equal(enabled.config.upload_pdf,false);
  await click('[data-tool=alpha]');await caption('Discover and bookmark papers in alphaXiv inside RN.','演示收藏为两篇虚构论文，不打开任何真实账号。');await hold(2.2);await shot('03-bookmarks');
  await caption('RN deduplicates and archives metadata, notes, and PDFs.','点击归档，运行真实 RN 引擎；外部接口由离线模拟服务提供。');await click('#sync-button');
  await until(async()=>{const s=await api('/api/status');return !s.busy&&s.jobs.length===2&&s.jobs.every(j=>j.status==='linked_archived');},'Template archive failed');
  const initial=JSON.parse(fs.readFileSync(path.join(runRoot,'data','demo-zotero.json'),'utf8'));assert.equal(initial.create_count,6);
  const pdfs=fs.readdirSync(path.join(runRoot,'demo-drive','Research PDFs')).filter(n=>n.endsWith('.pdf'));assert.equal(pdfs.length,2);
  await click('[data-page=archive]');await hold(2.4);await shot('04-archive');
  await caption('Run again: the same two papers, no duplicate imports.','再次运行，仍为两篇文献、两个 PDF；未新增重复条目。');await click('#sync-button');
  await until(async()=>!(await api('/api/status')).busy,'Repeat run still busy');
  const again=JSON.parse(fs.readFileSync(path.join(runRoot,'data','demo-zotero.json'),'utf8'));assert.equal(again.create_count,initial.create_count);assert.equal((await api('/api/status')).jobs.length,2);await hold(1.7);
  await click('[data-tool=zotero]');await caption('Read and annotate in your local Zotero window inside RN.','此处为归档结果示意；正式使用打开本机 Zotero 窗口。');await hold(2.5);await shot('05-zotero');
  await click('[data-tool=openresearch]');await caption('Continue in OpenResearch, in the same RN workspace.','手动把选中的论文链接 / PDF 交给研究对话，使用自己的 Agent。');await hold(3);await shot('06-openresearch');
  await click('[data-page=systems]');await until(()=>wc.executeJavaScript('!!document.querySelector(".system-map")'),'System overview not restored');
  await caption('Start with a template. Extend it in the DIY designer.','先使用系统模板，再通过 DIY 设计器扩展数据流。');await hold(2.5);
  if(testOnly){
    await click('[data-page=designer]');await until(()=>wc.executeJavaScript('!!document.querySelector(".flow-canvas")'),'DIY canvas missing');await delay(350);await shot('08-diy-canvas');
    const controls=await wc.executeJavaScript(`(()=>{const d=document.querySelector('#research-setup-dialog'),f=d.querySelector('form');d.showModal();f.elements.auto_discover.checked=true;f.elements.auto_discover.dispatchEvent(new Event('change',{bubbles:true}));f.elements.classifier.value='codex';return{projectsDisabled:f.elements.projects.disabled,projectsNotRequired:!f.elements.projects.required,futureConsentVisible:!document.querySelector('#research-future-consent').hidden,futureConsentUnchecked:!f.elements.allow_future_model_context.checked};})()`);
    assert.deepEqual(controls,{projectsDisabled:true,projectsNotRequired:true,futureConsentVisible:true,futureConsentUnchecked:true});
    await delay(350);await shot('09-project-onboarding');
    assert.equal(await wc.executeJavaScript(`(()=>{const d=document.querySelector('#research-setup-dialog'),f=d.querySelector('form');f.elements.auto_discover.checked=false;f.elements.auto_discover.dispatchEvent(new Event('change',{bubbles:true}));const valid=!f.elements.projects.disabled&&f.elements.projects.required&&document.querySelector('#research-future-consent').hidden;d.close();return valid;})()`),true);
  }
  const rejected=await fetch(address+'/api/designer/build',{method:'POST',headers:{Origin:address,'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'});assert.equal(rejected.status,400);
  if(testOnly){await click('[data-page=systems]');await until(()=>wc.executeJavaScript('!!document.querySelector(".system-map")'),'System page missing');}
  nativeTheme.themeSource='dark';await delay(450);await hold(.5);await shot('07-dark');
  await caption('Research Nexus. Your tools, one research system.','由 Rui Li（@shwhwhwh）创建和维护 · MIT 开源。');await hold(2.5);
  assert.deepEqual(blocked,[]);
  if(encoder){encoder.stdin.end();const [code]=await encoderExit;if(code!==0)throw Error(encoderError);}
  const report={passed:true,isolated_storage:true,simulated_services:true,real_archive_engine:true,real_accounts_opened:false,external_network_disabled:true,template_download_import:true,setup_required_before_enable:true,daily_interval:86400,papers:2,pdf_files:2,repeat_creates_no_duplicates:true,diy_canvas_available:true,diy_invalid_request_rejected:true,frames,duration_seconds:frames/12,checkpoints};
  fs.writeFileSync(path.join(runRoot,'report.json'),JSON.stringify(report,null,2));
  if(!testOnly)fs.copyFileSync(path.join(runRoot,'01-overview.png'),path.join(assets,'demo-poster.png'));
  console.log(JSON.stringify({...report,checkpoints:undefined,runRoot}));await cleanup();app.quit();
}).catch(async error=>{fs.writeFileSync(path.join(runRoot,'error.txt'),error.stack||String(error));console.error(error.message);await cleanup();app.exit(1);});
