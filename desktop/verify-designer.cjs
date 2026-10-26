// Hidden integration UI; separate archive database, profile and graph.
const {app,BrowserWindow,ipcMain,nativeTheme}=require('electron');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),testRoot=path.join(root,'data','designer-ui-test-'+Date.now());
fs.mkdirSync(path.join(testRoot,'web'),{recursive:true});
for(const file of ['index.html','app.js','appearance.js','style.css','designer.js','designer.css','icon.png','icon.svg'])fs.copyFileSync(path.join(root,'web',file),path.join(testRoot,'web',file));
app.setPath('userData',path.join(testRoot,'profile'));
app.on('window-all-closed',()=>{});
let win,backend,address,csrf;
const delay=ms=>new Promise(ok=>setTimeout(ok,ms));
async function until(predicate,message){const start=Date.now();while(Date.now()-start<10000){try{if(await predicate())return;}catch{}await delay(60);}throw Error(message);}
async function shutdown(){
  if(address&&csrf)await fetch(address+'/api/shutdown',{method:'POST',headers:{Origin:address,'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}).catch(()=>{});
  if(win&&!win.isDestroyed())win.destroy();
  if(backend&&backend.exitCode===null)await Promise.race([new Promise(ok=>backend.once('exit',ok)),delay(2000)]);
  if(backend&&backend.exitCode===null)backend.kill();
}
app.whenReady().then(async()=>{
  let runtime={};
  try {runtime=JSON.parse(fs.readFileSync(path.join(root,'runtime.local.json'),'utf8'));}catch{}
  const python=process.env.RESEARCH_NEXUS_PYTHON||process.env.RESEARCH_BRIDGE_PYTHON||runtime.python||'python';
  address=await new Promise((resolve,reject)=>{
    backend=spawn(python,['-u','-m','bridge.server','--root',testRoot],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
    let buffer='';backend.stdout.on('data',chunk=>{buffer+=chunk;for(const line of buffer.split('\n')){try{const msg=JSON.parse(line);if(msg.ready)resolve(msg.url);}catch{}}});
    backend.on('error',reject);backend.once('exit',code=>reject(Error('Test backend exited: '+code)));
    setTimeout(()=>reject(Error('Backend timed out')),10000).unref();
  });
  const html=await fetch(address).then(r=>r.text());csrf=html.match(/name="csrf-token" content="([^"]+)"/)[1];
  ipcMain.handle('workspace-state',()=>({tool:null,fullscreen:false}));ipcMain.handle('hide-tool',()=>{});
  ipcMain.handle('appearance-get',()=>({source:nativeTheme.themeSource,dark:nativeTheme.shouldUseDarkColors}));
  win=new BrowserWindow({show:false,width:1440,height:1040,webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false}});
  nativeTheme.on('updated',()=>win.webContents.send('appearance-state',{source:nativeTheme.themeSource,dark:nativeTheme.shouldUseDarkColors}));
  const wc=win.webContents,errors=[];
  wc.on('console-message',(...args)=>{const text=args.map(a=>typeof a==='string'?a:a?.message||'').join(' ');if(/Content Security Policy|Uncaught|TypeError/.test(text))errors.push(text);});
  await win.loadURL(address);
  await wc.insertCSS('* { transition:none!important; animation:none!important; }');
  await until(()=>wc.executeJavaScript('!!document.querySelector(".hero h1")'),'Dashboard not loaded');
  await wc.executeJavaScript('document.querySelector("[data-page=designer]").click()');
  await until(()=>wc.executeJavaScript('document.querySelectorAll(".flow-node").length===3'),'Designer did not render default nodes');
  async function center(selector){return wc.executeJavaScript(`(()=>{const b=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return{x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)}})()`);}
  const from=await center('[data-node=alphaxiv] .output'),to=await center('[data-node=openresearch] .input');
  wc.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...from});
  wc.sendInputEvent({type:'mouseMove',...to});wc.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...to});
  await until(()=>wc.executeJavaScript('document.querySelectorAll("[data-edge]").length===2'),'Dragging a connector did not create an edge');
  const nodeCenter=await center('[data-node=zotero] .flow-node-body');
  const before=await wc.executeJavaScript('document.querySelector("[data-node=zotero]").getAttribute("transform")');
  wc.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...nodeCenter});
  wc.sendInputEvent({type:'mouseMove',x:nodeCenter.x+45,y:nodeCenter.y+35});
  wc.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,x:nodeCenter.x+45,y:nodeCenter.y+35});
  await delay(120);assert.notEqual(await wc.executeJavaScript('document.querySelector("[data-node=zotero]").getAttribute("transform")'),before);
  await wc.executeJavaScript('document.querySelector("[data-d=demo]").click()');
  assert.equal(await wc.executeJavaScript('document.querySelectorAll(".flow-node").length'),5);
  await wc.executeJavaScript(`document.querySelector('[data-edge-field=purpose]').value='按 arxiv 去重并保存阅读清单';document.querySelector('[data-edge-field=purpose]').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-edge-field=purpose]').focus();globalThis.savedEditor=document.querySelector('[data-edge-field=purpose]');`);
  await delay(4400);
  assert.equal(await wc.executeJavaScript('savedEditor===document.querySelector("[data-edge-field=purpose]")&&savedEditor.value==="按 arxiv 去重并保存阅读清单"'),true,'Polling must not replace a focused draft');
  await wc.executeJavaScript('document.querySelector("[data-d=save]").click()');
  await until(()=>wc.executeJavaScript('document.querySelector("#designer-save-state").textContent.includes("已保存")'),'Graph save failed');
  const graph=await fetch(address+'/api/designer').then(r=>r.json());
  assert.equal(graph.project.nodes.length,5);assert.equal(graph.project.edges.length,3);
  assert(graph.project.edges.some(e=>e.purpose==='按 arxiv 去重并保存阅读清单'));
  await wc.executeJavaScript("document.activeElement.blur();document.querySelector('.flow-sample').open=true");
  await delay(2500);
  await wc.executeJavaScript("document.querySelector('.flow-sample').open=true");
  await delay(2500);
  assert.equal(await wc.executeJavaScript("document.querySelector('.flow-sample').open"),true,'Status polling must preserve expanded inspection details');
  const forbidden=await fetch(address+'/api/designer/save',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});assert.equal(forbidden.status,403);
  const geometry=await wc.executeJavaScript(`(()=>{const board=document.querySelector('.flow-canvas').getBoundingClientRect();const panel=document.querySelector('.designer-inspector').getBoundingClientRect();const input=getComputedStyle(document.querySelector('[data-edge-field=purpose]'));return{width:innerWidth,board:{x:board.x,y:board.y,width:board.width,height:board.height},panel:{x:panel.x,width:panel.width},font:input.fontSize,pageOverflow:document.documentElement.scrollWidth>innerWidth}})()`);
  assert(geometry.board.width>500);assert(geometry.board.height>300);assert.equal(geometry.font,'14px');assert.equal(geometry.pageOverflow,false);
  for(const theme of ['light','dark']){
    nativeTheme.themeSource=theme;
    await until(()=>wc.executeJavaScript(`document.documentElement.dataset.theme===${JSON.stringify(theme)}`),'Theme did not change');
    await delay(250);
    // A hidden compositor can return its previous frame on the first capture.
    let shot;
    for(let attempt=0;attempt<8;attempt++) {
      shot=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
      const pixel=shot.crop({x:250,y:80,width:1,height:1}).toBitmap()[0];
      if(theme==='light'?pixel>235:pixel<65)break;
      await delay(120);
    }
    const brightness=shot.crop({x:250,y:80,width:1,height:1}).toBitmap()[0];
    assert(theme==='light'?brightness>235:brightness<65,'Captured compositor frame must match '+theme);
    fs.writeFileSync(path.join(root,'data','designer-'+theme+'.png'),shot.toPNG());
  }
  assert.deepEqual(errors,[]);
  const report={passed:true,isolated_backend:true,live_accounts_untouched:true,drag_to_connect:true,node_drag:true,sample_flow:true,graph_persisted:true,polling_preserves_drafts:true,polling_preserves_details:true,csrf_enforced:true,light_dark_verified:true,geometry};
  fs.writeFileSync(path.join(root,'data','designer-ui-acceptance.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  await shutdown();app.quit();
}).catch(async error=>{console.error(error);fs.writeFileSync(path.join(root,'data','designer-ui-error.txt'),error.stack||String(error));await shutdown();app.exit(1);});
