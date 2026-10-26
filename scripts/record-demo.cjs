// Records ONLY an isolated Research Nexus webContents, never the desktop.
// Requires FFmpeg in RN_DEMO_FFMPEG or on PATH. All displayed records are fictional.
const {app, BrowserWindow, ipcMain, nativeTheme} = require('electron');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const root = path.resolve(__dirname, '..');
const demoRoot = path.join(root, 'artifacts', 'demo-' + Date.now());
const assets = path.join(root, 'docs', 'assets');
fs.mkdirSync(path.join(demoRoot, 'web'), {recursive:true});
fs.mkdirSync(path.join(demoRoot, 'data', 'designer'), {recursive:true});
fs.mkdirSync(assets, {recursive:true});
for (const file of ['index.html','style.css','app.js','appearance.js','designer.js','designer.css','icon.png','icon.svg']) {
  let bytes = fs.readFileSync(path.join(root, 'web', file));
  if (file === 'index.html') {
    let html = bytes.toString().replace(/<div class="nav-caption tools-caption">[\s\S]*?<\/nav>/, '');
    html = html.replace('收藏 → 去重 → 归档','DIY research system');
    bytes = Buffer.from(html);
  }
  if (file === 'designer.js') {
    // Present local artifact locations without exposing internal template IDs.
    bytes = Buffer.from(bytes.toString().replace('JSON.stringify(focus.result,null,2)', 'JSON.stringify(focus.result,(key,value)=>key==="path"?"Local output folder":value,2)'));
  }
  fs.writeFileSync(path.join(demoRoot, 'web', file), bytes);
}
// The internal IDs preserve the initial template contract; no personal data is copied.
const fictional = [
  {title:'Demo paper: Tiny robots',arxiv:'DEMO-001'},
  {title:'Demo paper: Learning agents',arxiv:'DEMO-002'},
  {title:'Demo paper: Tiny robots',arxiv:'DEMO-001'}
];
const project = {id:'public-demo',name:'Demo research system',revision:1,activation:'review',
  nodes:[
    {id:'alphaxiv',name:'Paper Source',kind:'folder',description:'Fictional sample JSON, no network',x:65,y:155},
    {id:'zotero',name:'Reading List',kind:'folder',description:'Local Markdown output',x:410,y:155},
    {id:'openresearch',name:'Experiment Board',kind:'folder',description:'A place for your next connection',x:410,y:390}
  ],edges:[{id:'existing-archive',source:'alphaxiv',target:'zotero',purpose:'',data_type:'Sample JSON → Markdown',sample:fictional,schedule:'manual'}],
  active:{},versions:{},last_run:{}};
fs.writeFileSync(path.join(demoRoot,'data','designer','project.json'),JSON.stringify(project));
fs.writeFileSync(path.join(demoRoot,'data','config.json'),JSON.stringify({auto_sync:false,zotero_user_id:'',openresearch_exe:''}));
app.setPath('userData',path.join(demoRoot,'profile'));
app.on('window-all-closed',()=>{});
nativeTheme.themeSource='light';
let backend, win, encoder, address, csrf, frames=0, recording=false, captionText='', encoderExit;
const checkpoints=[];
const delay=ms=>new Promise(ok=>setTimeout(ok,ms));
async function until(fn,message,timeout=20000) {const start=Date.now();while(Date.now()-start<timeout){if(await fn())return;await delay(120);}throw Error(message);}
async function api(route,payload) {
  const response=await fetch(address+route,payload===undefined?{}:{method:'POST',headers:{Origin:address,'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});
  const data=await response.json();if(!response.ok)throw Error(data.error||route);return data;
}
async function cleanup() {
  if(encoder&&!encoder.stdin.destroyed)encoder.stdin.end();
  if(address&&csrf)await api('/api/shutdown',{}).catch(()=>{});
  if(win&&!win.isDestroyed())win.destroy();
  if(backend&&backend.exitCode===null)await Promise.race([once(backend,'exit'),delay(2500)]);
  if(backend&&backend.exitCode===null)backend.kill();
}
app.whenReady().then(async()=>{
  let configured={};try{configured=JSON.parse(fs.readFileSync(path.join(root,'runtime.local.json'),'utf8'));}catch{}
  const python=process.env.RESEARCH_NEXUS_PYTHON||configured.python||'python';
  // Remove service credentials from the child environment. CLI auth stays in its own store.
  const childEnv={...process.env};
  for(const key of Object.keys(childEnv))if(/ALPHAXIV|ZOTERO|RN_.*(?:KEY|TOKEN)|RESEARCH_BRIDGE/.test(key))delete childEnv[key];
  backend=spawn(python,['-u','-m','bridge.server','--root',demoRoot],{cwd:root,env:childEnv,windowsHide:true,stdio:['ignore','pipe','pipe']});
  backend.stderr.on('data',chunk=>fs.appendFileSync(path.join(demoRoot,'backend.log'),chunk));
  address=await new Promise((resolve,reject)=>{
    let buffer='';backend.stdout.on('data',chunk=>{buffer+=chunk;for(const line of buffer.split('\n'))try{const message=JSON.parse(line);if(message.ready)resolve(message.url);}catch{}});
    backend.on('error',reject);backend.on('exit',code=>reject(Error('Isolated backend exited '+code)));
    setTimeout(()=>reject(Error('Isolated backend timeout')),20000).unref();
  });
  csrf=(await fetch(address).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)[1];
  ipcMain.handle('workspace-state',()=>({tool:null,fullscreen:false}));
  ipcMain.handle('hide-tool',()=>{});
  ipcMain.handle('appearance-get',()=>({source:nativeTheme.themeSource,dark:nativeTheme.shouldUseDarkColors}));
  ipcMain.handle('appearance-set',(_event,source)=>{nativeTheme.themeSource=source;return{source,dark:nativeTheme.shouldUseDarkColors};});
  win=new BrowserWindow({show:false,width:1440,height:1000,useContentSize:true,webPreferences:{preload:path.join(root,'desktop','preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,backgroundThrottling:false}});
  const wc=win.webContents;
  nativeTheme.on('updated',()=>wc.send('appearance-state',{source:nativeTheme.themeSource,dark:nativeTheme.shouldUseDarkColors}));
  await win.loadURL(address);
  await until(()=>wc.executeJavaScript('!!document.querySelector(".hero h1")'),'RN did not start');
  await wc.insertCSS(`*{transition:none!important;animation:none!important}.top-actions,.window-controls{display:none!important}body.designer-open #main{height:calc(100vh - 150px)}#demo-caption{position:fixed;bottom:0;left:236px;right:0;height:94px;box-sizing:border-box;background:var(--surface);border-top:1px solid var(--border);z-index:9999;padding:15px 28px;color:var(--ink);font:510 18px/28px "Segoe UI",sans-serif}#demo-caption small{display:block;font-size:13px;font-weight:400;color:var(--muted)}#demo-badge{position:fixed;left:250px;top:15px;z-index:9999;color:var(--muted);font:12px "Segoe UI",sans-serif;background:var(--bg);padding:4px 8px}#demo-cursor{position:fixed;width:16px;height:16px;border:2px solid #7a8df2;background:#9aacff45;border-radius:50%;box-shadow:0 0 0 4px #8a9bff18;z-index:10001;pointer-events:none;transform:translate(-50%,-50%)}.demo-result{position:absolute;inset:26px;z-index:4;background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:28px;color:var(--ink);box-shadow:0 15px 50px #0001}.demo-result h2{font-size:23px;margin:8px 0 20px}.demo-result pre{font:15px/28px "Segoe UI",sans-serif;white-space:pre-wrap}.demo-result .metric{display:inline-block;border-radius:10px;background:var(--green-light);color:var(--green);padding:12px 16px;margin:16px 0}`);
  await wc.executeJavaScript(`document.querySelector('[data-page=designer]').click();document.querySelector('.breadcrumb').style.visibility='hidden';document.body.insertAdjacentHTML('beforeend','<div id="demo-caption"></div><div id="demo-badge">ISOLATED DEMO · FICTIONAL DATA · NO ACCOUNTS CONNECTED</div><div id="demo-cursor" style="left:900px;top:350px"></div>')`);
  await until(()=>wc.executeJavaScript('document.querySelectorAll(".flow-node").length===3'),'Designer not ready');
  // Flush the initial dashboard frame before recording the designer.
  for(let warm=0;warm<8;warm++) {
    const image=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
    if(warm>=2&&image.crop({x:1230,y:28,width:1,height:1}).toBitmap()[0]>235)break;
    await delay(180);
  }
  const video=path.join(assets,'research-nexus-demo.mp4');
  encoder=spawn(process.env.RN_DEMO_FFMPEG||'ffmpeg',['-y','-hide_banner','-loglevel','error','-f','image2pipe','-vcodec','mjpeg','-framerate','12','-i','pipe:0','-vf','scale=1440:1000','-an','-c:v','libx264','-preset','medium','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',video],{windowsHide:true,stdio:['pipe','ignore','pipe']});
  let encoderErrors='';encoder.stderr.on('data',chunk=>encoderErrors+=chunk);encoder.on('error',error=>{encoderErrors+=error.message;});encoderExit=once(encoder,'exit');
  encoder.stdin.on('error',()=>{});
  async function frame(){
    if(encoder.exitCode!==null)throw Error('Video encoder failed: '+encoderErrors);
    // Let the hidden Chromium compositor paint between captures. Without this,
    // rapid captures can encode an older frame after a DOM change.
    await delay(1000/12);
    const pixels=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
    if(!encoder.stdin.write(pixels.toJPEG(88)))await once(encoder.stdin,'drain');frames++;
  }
  async function hold(seconds){for(let i=0;i<Math.round(seconds*12);i++)await frame();}
  async function caption(english,chinese){captionText=english+' | '+chinese;await wc.executeJavaScript(`document.querySelector('#demo-caption').replaceChildren(Object.assign(document.createElement('span'),{textContent:${JSON.stringify(english)}}),Object.assign(document.createElement('small'),{textContent:${JSON.stringify(chinese)}}))`);checkpoints.push({frame:frames,seconds:frames/12,english,chinese});}
  async function position(selector){return wc.executeJavaScript(`(()=>{const b=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)}})()`);}
  async function cursor(point){await wc.executeJavaScript(`(()=>{Object.assign(document.querySelector('#demo-cursor').style,{left:'${point.x}px',top:'${point.y}px'});})()`);}
  async function click(selector){await wc.executeJavaScript(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'center',inline:'nearest'})`);await delay(100);const point=await position(selector);await cursor(point);await hold(.35);wc.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...point});wc.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...point});await delay(200);}
  async function input(selector,value){await click(selector);await wc.executeJavaScript(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
  async function checkpoint(name){await frame();await delay(140);const image=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});fs.writeFileSync(path.join(demoRoot,name+'.png'),image.toPNG());const visible=await wc.executeJavaScript('document.body.innerText');assert(!/alphaXiv|Zotero|OpenResearch/i.test(visible),'Third-party surface visible');checkpoints.push({name,frame:frames,visible});}
  recording=true;
  await caption('Your research. Connected.','Research Nexus：让工具组成你的科研系统。');
  await checkpoint('01-overview');await hold(3);
  await caption('Add the tools you want to work with.','添加网页、API、本地应用或输出目录。');
  await click('[data-d=add]');await hold(1);
  await input('[name=name]','Lab Notebook');await input('[name=kind]','folder');await input('[name=description]','Fictional notes for a DIY research system');await hold(1.7);
  await click('#designer-add-form button[type=submit]');await hold(1.5);
  await caption('Draw a connection to describe the next handoff.','从输出圆点拖到输入圆点，自定义数据流向。');
  const from=await position('[data-node=zotero] .output');
  const newId=await wc.executeJavaScript('Array.from(document.querySelectorAll(".flow-node")).map(n=>n.dataset.node).find(id=>id.startsWith("tool-"))');
  const to=await position(`[data-node="${newId}"] .input`);
  await cursor(from);await hold(.5);wc.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...from});
  for(let i=1;i<=18;i++){const point={x:Math.round(from.x+(to.x-from.x)*i/18),y:Math.round(from.y+(to.y-from.y)*i/18)};wc.sendInputEvent({type:'mouseMove',...point});await cursor(point);await frame();}
  wc.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...to});await delay(200);
  assert.equal(await wc.executeJavaScript('document.querySelectorAll("[data-edge]").length'),2);
  await hold(1.4);await checkpoint('02-connected');
  await caption('Tell RN what a connection should do.','用一句话说明用途，再交给本地 Agent。');
  await click('[data-edge=existing-archive] .flow-edge-line');
  const purpose='Use the provided sample JSON only. Deduplicate by arxiv. Preserve title and arxiv in a Markdown reading list. Write reading-list.md. No network requests.';
  await input('[data-edge-field=purpose]',purpose);await hold(2.5);await click('[data-d=save]');await hold(1);
  await caption('Generate a plan with your local agent.','实际调用本地 Codex；生成等待过程已剪短。');
  await click('[data-d=build]');await hold(2);
  // Do not record a long wait or any CLI terminal. Only RN's safe plan appears.
  let build;
  await until(async()=>{const state=await api('/api/designer');build=state.runs.find(r=>r.kind==='build');if(build?.status==='error')throw Error(build.error);return build?.status==='candidate';},'Agent did not produce a plan',380000);
  await until(()=>wc.executeJavaScript('!!document.querySelector("#designer-version")&&!document.querySelector("[data-d=build]").disabled'),'Plan not rendered');
  await wc.executeJavaScript('document.querySelector("#designer-version").scrollIntoView({block:"center"})');
  await checkpoint('03-plan');await hold(3);
  await caption('Preview safely with fictional sample data.','先测试与预览，确认三条样例去重为两条。');
  await click('[data-d=test]');await until(async()=>{const state=await api('/api/designer');return state.runs.some(r=>r.kind==='test'&&r.status==='tested');},'Fixture preview failed');
  await until(()=>wc.executeJavaScript('!document.querySelector("[data-d=activate]").disabled'),'Test UI not ready');
  await checkpoint('04-tested');await hold(3);
  await caption('Enable the reviewed version. Then run.','检查方案后启用指定版本，再执行这条连线。');
  await click('[data-d=activate]');await until(()=>wc.executeJavaScript('!!document.querySelector("[data-d=run-edge]")'),'Activation UI not ready');await hold(1.5);
  await click('[data-d=run-edge]');
  await until(async()=>{const state=await api('/api/designer');return state.runs.some(r=>r.kind==='execute'&&r.status==='success');},'Real local output failed');
  const output=path.join(demoRoot,'data','designer','outputs','zotero','reading-list.md');
  const first=fs.readFileSync(output,'utf8');assert(first.includes('DEMO-001')&&first.includes('DEMO-002'));assert.equal((first.match(/DEMO-001/g)||[]).length,1);
  await delay(2500);
  await click('[data-d=run-edge]');
  await until(async()=>{const state=await api('/api/designer');return state.runs.filter(r=>r.kind==='execute'&&r.status==='success').length===2;},'Repeat run failed');
  assert.equal(fs.readFileSync(output,'utf8'),first,'Repeated execution must preserve the same artifact');
  await caption('3 sample records → 2 unique notes. Repeat: unchanged.','已真实生成 Markdown；再次运行内容保持一致，没有重复追加。');
  await wc.executeJavaScript(`document.querySelector('.designer-board').insertAdjacentHTML('beforeend','<div class="demo-result"><div class="designer-eyebrow">VERIFIED LOCAL OUTPUT</div><h2>From a connection to a useful artifact.</h2><div class="metric">3 input records → 2 unique notes · repeat verified</div><pre></pre><p>Fictional sample data · No external service writes</p></div>');document.querySelector('.demo-result pre').textContent=${JSON.stringify(first)}`);
  await checkpoint('05-output');await hold(4);
  await wc.executeJavaScript('document.querySelector(".demo-result").remove()');
  await caption('Make the workspace yours.','支持浅色、深色和跟随系统。');
  nativeTheme.themeSource='dark';await delay(500);await frame();await frame();await checkpoint('06-dark');await hold(3);
  await caption('Design. Review. Run. Improve.','Research Nexus · 由 Rui Li（@shwhwhwh）创建 · MIT 开源');
  await wc.executeJavaScript('document.querySelector("[data-d=deselect]")?.click();document.querySelector("[data-d=fit]").click()');
  await hold(3);
  recording=false;encoder.stdin.end();
  const [exitCode]=await encoderExit;if(exitCode!==0)throw Error(encoderErrors);
  const report={recorded_product_window_only:true,isolated_storage:true,fictional_data_only:true,third_party_windows_opened:false,real_local_agent:true,agent_wait_trimmed:true,fixture_records:3,unique_records:2,repeated_output_unchanged:true,frames,framerate:12,duration_seconds:frames/12,checkpoints};
  fs.writeFileSync(path.join(demoRoot,'report.json'),JSON.stringify(report,null,2));
  // Use a reviewed overview as the public poster; no terminal or desktop capture.
  fs.copyFileSync(path.join(demoRoot,'01-overview.png'),path.join(assets,'demo-poster.png'));
  console.log(JSON.stringify({passed:true,video,demoRoot,duration:frames/12,frames}));
  await cleanup();app.quit();
}).catch(async error=>{recording=false;fs.writeFileSync(path.join(demoRoot,'error.txt'),error.stack||String(error));console.error(error.message);await cleanup();app.exit(1);});
