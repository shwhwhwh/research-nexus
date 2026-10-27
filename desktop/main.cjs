const { app, BrowserWindow, ipcMain, dialog, Menu, nativeImage, Tray, screen, shell, nativeTheme } = require('electron');
const NativeApps = require('./native-apps.cjs');
const {ToolViews} = require('./tool-views.cjs');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
app.setName('Research Nexus');
app.setPath('userData', path.join(root, 'data', 'desktop'));
app.setAppUserModelId('local.research.nexus');
const appearanceFile=path.join(root,'data','appearance.json');
let themeSource='system';
try {const saved=JSON.parse(fs.readFileSync(appearanceFile,'utf8'));if(['system','light','dark'].includes(saved.source))themeSource=saved.source;}catch{}
nativeTheme.themeSource=themeSource;
const appearance=()=>({source:themeSource,dark:nativeTheme.shouldUseDarkColors});
let win, backend, origin, activeTool, backendLog, trayIcon, trayMenu;
let shuttingDown = false, serverCSRF = '';
const createQuitGuard=require('./quit-guard.cjs');
const quitGuard=createQuitGuard({cleanup:shutdown,quit:()=>app.quit(),onStart:()=>{shuttingDown=true;},onError:error=>{
  shuttingDown=false;
  dialog.showErrorBox('暂未退出 Research Nexus',error.message+'\n为保护 Zotero 和 OpenResearch 窗口，工作台仍在运行。请稍后从托盘重试退出。');
}});
let nativeApps, webTools;
let workspaceReady=false, openResearchRequested=process.argv.includes('--open-openresearch');
let designerRequested=process.argv.includes('--open-designer');
let systemsRequested=process.argv.includes('--open-systems');
const isNativeTool = tool => ['zotero','openresearch'].includes(tool);
const views = new Map();
const customTools = new Map();
const smokeTray = process.argv.includes('--smoke-tray');
const smokeFullscreen = process.argv.includes('--smoke-fullscreen');
if (smokeFullscreen) app.setPath('userData', path.join(root, 'data', 'desktop-fullscreen-test'));
const smoke = process.argv.includes('--smoke-test') || smokeTray || smokeFullscreen;
const smokeTools = process.argv.includes('--smoke-tools');
const single = app.requestSingleInstanceLock();
if (!single) app.quit();
else {
  app.on('second-instance', (_event,args)=>{
    showWorkspace();
    if(args.includes('--open-systems')) {
      if(!workspaceReady)systemsRequested=true;
      else win.webContents.send('open-systems');
    }
    if(args.includes('--open-designer')) {
      if(!workspaceReady)designerRequested=true;
      else win.webContents.send('open-designer');
    }
    if(args.includes('--open-openresearch')) {
      if(!workspaceReady)openResearchRequested=true;
      else launchOpenResearch().catch(e=>dialog.showErrorBox('OpenResearch',e.message));
    }
  });
  app.whenReady().then(start).catch(async e => {
    fs.mkdirSync(path.join(root, 'data'), { recursive: true });
    fs.writeFileSync(path.join(root, 'data', 'startup-error.txt'), String(e));
    if (!smoke) dialog.showErrorBox('Research Nexus 启动失败', String(e));
    try {await nativeApps?.detach();app.exit(1);}
    catch(error) {dialog.showErrorBox('本地窗口尚未释放',error.message);}
  });
}

function showWorkspace() {
  if (!win || win.isDestroyed()) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, 'nexus-aurora-soft-rainbow.ico'));
  if (icon.isEmpty()) throw new Error('无法加载托盘图标，工作台未进入隐藏模式。');
  trayIcon = new Tray(icon);
  trayIcon.setToolTip('Research Nexus · 关闭窗口后继续运行');
  trayMenu = Menu.buildFromTemplate([
    { id:'show-workspace', label:'打开 Research Nexus', click:showWorkspace },
    { label:'打开 OpenResearch', click:launchOpenResearch },
    { label:'隐藏到托盘', click:()=>{if(win && !win.isDestroyed())win.hide();} },
    { type:'separator' },
    { label:'关闭窗口后继续后台归档', enabled:false },
    { type:'separator' },
    { id:'quit-workspace', label:'退出 Research Nexus', click:()=>app.quit() }
  ]);
  trayIcon.setContextMenu(trayMenu);
  trayIcon.on('click', showWorkspace);
  trayIcon.on('double-click', showWorkspace);
}
function launchOpenResearch() {
  showWorkspace();
  return showNativeTool('openresearch');
}

function ownSender(event) {
  if (!win || event.sender !== win.webContents || new URL(event.senderFrame.url).origin !== origin) throw new Error('Untrusted sender');
}
function layout() {
  if (!win || win.isDestroyed()) return;
  const [width, height] = win.getContentSize();
  const x = win.isFullScreen() ? 0 : 236, y = win.isFullScreen() ? 0 : 56;
  webTools?.layout({x,y,width:Math.max(1,width-x),height:Math.max(1,height-y)},activeTool,win.isVisible()&&!win.isMinimized());
  const content=win.getContentBounds();
  nativeApps?.layout(screen.dipToScreenRect(win,{x:content.x+x,y:content.y+y,width:Math.max(1,width-x),height:Math.max(1,height-y)}),isNativeTool(activeTool)?activeTool:'',win.isVisible()&&!win.isMinimized());
}
async function showNativeTool(tool, itemKey) {
  if(shuttingDown)throw new Error('正在安全退出 Research Nexus，请稍后重新打开工具。');
  if(!isNativeTool(tool))throw new Error('不支持的本地应用。');
  void webTools?.checkpoint();
  await nativeApps.connect();activeTool=tool;layout();
  const result=await nativeApps.open(tool);
  if(tool==='zotero'&&itemKey) {
    if(!/^[A-Z0-9]{8}$/.test(itemKey))throw new Error('无效的 Zotero 条目编号。');
    await shell.openExternal('zotero://select/library/items/'+itemKey);
  }
  return result;
}
function toggleFullscreen() {
  if (!win || win.isDestroyed()) return;
  win.setFullScreen(!win.isFullScreen());
  layout();
}
function bindFullscreenKeys(contents) {
  // Each embedded page receives its own keyboard events, including after navigation.
  contents.on('before-input-event', (event, input) => {
    if (input.key !== 'F11' || input.control || input.alt || input.meta || input.shift) return;
    event.preventDefault();
    if (input.type === 'keyDown' && !input.isAutoRepeat) toggleFullscreen();
  });
}
function isAllowed(tool, address) {
  try {
    const u = new URL(address);
    if(tool.startsWith('custom-'))return ['https:','http:'].includes(u.protocol)&&u.origin===new URL(customTools.get(tool)?.url).origin&&!u.username&&!u.password;
    if (tool === 'alpha') return u.protocol === 'https:' && ['www.alphaxiv.org','alphaxiv.org'].includes(u.hostname);
    if (tool === 'zotero') return u.protocol === 'https:' && ['www.zotero.org','zotero.org'].includes(u.hostname);
    if (tool === 'openresearch') return u.protocol === 'http:' && ['127.0.0.1','localhost'].includes(u.hostname) && !u.username && !u.password;
    if (tool === 'pdf') return u.origin === origin && /^\/api\/pdf\/\d+$/.test(u.pathname);
  } catch {}
  return false;
}
function safeWebNavigation(url) {
  try { return ['https:', 'http:'].includes(new URL(url).protocol); } catch { return false; }
}
async function showTool(tool, address) {
  if(isNativeTool(tool))return showNativeTool(tool);
  if(activeTool==='alpha'&&tool!=='alpha')void webTools.checkpoint();
  const result=webTools.open(tool,address);
  activeTool = tool;
  layout();
  views.get(tool).webContents.focus();
  return result;
}
function startBackend() {
  fs.mkdirSync(path.join(root, 'data'), {recursive: true});
  backendLog = fs.openSync(path.join(root, 'data', 'backend.log'), 'a');
  const runtimeFile = path.join(root, 'runtime.local.json');
  const configured = fs.existsSync(runtimeFile) ? JSON.parse(fs.readFileSync(runtimeFile, 'utf8')) : {};
  const python = process.env.RESEARCH_NEXUS_PYTHON || process.env.RESEARCH_BRIDGE_PYTHON || configured.python || 'python';
  backend = spawn(python, ['-u', '-m', 'bridge.server', '--root', root], {cwd:root, windowsHide:true, stdio:['pipe','pipe',backendLog]});
  return new Promise((resolve, reject) => {
    let buffer = '', finished = false;
    const timer = setTimeout(() => { if (!finished) reject(new Error('后台服务启动超时')); }, 20000);
    backend.on('error', e => { clearTimeout(timer); reject(e); });
    backend.on('exit', code => {
      if (!finished) { clearTimeout(timer); reject(new Error(`后台服务退出 (${code})；请查看 data/backend.log`)); }
      else if (!shuttingDown && win && !win.isDestroyed()) dialog.showErrorBox('后台服务已退出', '请关闭并重新打开 Research Nexus。');
    });
    backend.stdout.on('data', data => {
      buffer += data.toString();
      let index;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0,index); buffer=buffer.slice(index+1);
        try { const msg=JSON.parse(line); if(msg.ready && msg.url && !finished) { finished=true; clearTimeout(timer); resolve(msg.url); } } catch {}
      }
    });
  });
}
async function start() {
  // Fullscreen acceptance borrows the running read-only dashboard, never its scheduler lifecycle.
  const address = smokeFullscreen ? JSON.parse(fs.readFileSync(path.join(root,'data','runtime.json'),'utf8')).url : await startBackend();
  origin = new URL(address).origin;
  const html = await (await fetch(address)).text();
  serverCSRF = html.match(/name="csrf-token" content="([^"]+)"/)?.[1] || '';
  Menu.setApplicationMenu(null);
  win = new BrowserWindow({width:1440,height:940,minWidth:1100,minHeight:700,show:!smoke,frame:false,icon:path.join(__dirname,'nexus-aurora-soft-rainbow.ico'),backgroundColor:nativeTheme.shouldUseDarkColors?'#1e1e21':'#ffffff',
    title:'Research Nexus', webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
  nativeTheme.on('updated',()=>{
    if(!win||win.isDestroyed())return;
    win.setBackgroundColor(nativeTheme.shouldUseDarkColors?'#1e1e21':'#ffffff');
    win.webContents.send('appearance-state',appearance());
  });
  nativeApps=new NativeApps(root,win);
  webTools=new ToolViews({win,root,views,isAllowed,safeWebNavigation,bindFullscreenKeys,onCreate:layout,
    onState:data=>{if(win&&!win.isDestroyed())win.webContents.send('tool-state',data);}});
  nativeApps.on('state',data=>{
    if(!win||win.isDestroyed()||shuttingDown)return;
    if(data.event==='fullscreen')toggleFullscreen();
    else if(data.event==='hide')win.close();
    else if(data.event==='activate') {activeTool=data.tool;showWorkspace();layout();}
    else if(['released','closed'].includes(data.event)&&activeTool===data.tool){activeTool=null;layout();}
    win.webContents.send('native-tool-state',data);
  });
  win.once('ready-to-show',()=>{if(!smoke && win && !win.isDestroyed())win.show();});
  if (!smoke || smokeTray) createTray();
  win.on('close',event=>{
    if (!quitGuard.allowed && (quitGuard.busy || (trayIcon && !trayIcon.isDestroyed()))) {
      event.preventDefault();
      void webTools.checkpoint();
      win.hide();
    }
  });
  win.webContents.setWindowOpenHandler(() => ({action:'deny'}));
  bindFullscreenKeys(win.webContents);
  win.webContents.on('will-navigate', (event,url) => { if(new URL(url).origin!==origin) event.preventDefault(); });
  win.on('resize',layout);
  for(const event of ['move','show','hide','minimize','restore','maximize','unmaximize'])win.on(event,layout);
  for (const event of ['enter-full-screen', 'leave-full-screen']) win.on(event, () => {
    layout();
    win.webContents.send('fullscreen-state', win.isFullScreen());
  });
  win.on('closed',()=>{webTools.stop(); for(const view of views.values()) if(!view.webContents.isDestroyed()) view.webContents.close(); win=null; });
  ipcMain.handle('show-tool',(event,{tool,url})=>{ownSender(event);return showTool(tool,url);});
  ipcMain.handle('hide-tool',event=>{ownSender(event);void webTools.checkpoint();activeTool=null;layout();});
  ipcMain.handle('workspace-state',event=>{ownSender(event);return {tool:activeTool||null,fullscreen:win.isFullScreen(),url:views.get(activeTool)?.webContents.getURL(),name:customTools.get(activeTool)?.name};});
  ipcMain.handle('appearance-get',event=>{ownSender(event);return appearance();});
  ipcMain.handle('appearance-set',(event,source)=>{
    ownSender(event);if(!['system','light','dark'].includes(source))throw new Error('无效的外观选项。');
    fs.writeFileSync(appearanceFile,JSON.stringify({source},null,2));themeSource=source;nativeTheme.themeSource=source;
    return appearance();
  });
  ipcMain.handle('window-action',(event,action)=>{
    ownSender(event);if(action==='minimize')win.minimize();
    else if(action==='maximize'){if(win.isMaximized())win.unmaximize();else win.maximize();}
    else if(action==='close')win.close();else throw new Error('无效的窗口操作。');
  });
  ipcMain.handle('toggle-fullscreen',event=>{ownSender(event);toggleFullscreen();return win.isFullScreen();});
  ipcMain.handle('launch-openresearch',event=>{ownSender(event);return launchOpenResearch();});
  ipcMain.handle('show-native-tool',(event,{tool,itemKey})=>{ownSender(event);return showNativeTool(tool,itemKey);});
  ipcMain.handle('release-native-tool',event=>{ownSender(event);return nativeApps.release(activeTool);});
  ipcMain.handle('zotero-account-settings',event=>{ownSender(event);return shell.openExternal('https://www.zotero.org/settings/keys');});
  ipcMain.handle('navigate-tool',(event,action)=>{
    ownSender(event); const wc=views.get(activeTool)?.webContents; if(!wc)return;
    if(action==='back' && wc.navigationHistory.canGoBack())wc.navigationHistory.goBack();
    if(action==='reload')wc.reload();
  });
  ipcMain.handle('launch-zotero',event=>{
    ownSender(event);
    return showNativeTool('zotero');
  });
  ipcMain.handle('choose-pdf-folder',async event=>{
    ownSender(event);
    const result=await dialog.showOpenDialog(win,{title:'选择 Google Drive 中的论文 PDF 文件夹',properties:['openDirectory']});
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('choose-tool-executable',async event=>{
    ownSender(event);
    const result=await dialog.showOpenDialog(win,{title:'选择本地科研应用',properties:['openFile'],filters:[{name:'Windows 应用',extensions:['exe']}]});
    return result.canceled?null:result.filePaths[0];
  });
  ipcMain.handle('choose-system-template',async event=>{
    ownSender(event);
    const result=await dialog.showOpenDialog(win,{title:'导入 Research Nexus System Template',properties:['openFile'],filters:[{name:'Research Nexus System Template',extensions:['json']}]});
    if(result.canceled)return null;
    const file=result.filePaths[0];if(fs.statSync(file).size>524288)throw Error('模板文件过大。');
    return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
  });
  ipcMain.handle('save-blueprint',async(event,jobId)=>{
    ownSender(event);if(typeof jobId!=='string'||!/^[a-f0-9]{32}$/.test(jobId))throw Error('构建编号无效。');
    const response=await fetch(origin+'/api/builder/template?id='+jobId);const manifest=await response.json();if(!response.ok)throw Error(manifest.error||'模板不可导出。');
    const result=await dialog.showSaveDialog(win,{title:'导出可复用科研系统模板',defaultPath:manifest.id+'.rn-system.json',filters:[{name:'Research Nexus Blueprint',extensions:['json']}]});
    if(result.canceled)return false;fs.writeFileSync(result.filePath,JSON.stringify(manifest,null,2)+'\n','utf8');return true;
  });
  ipcMain.handle('save-system-template',async(event,_manifest)=>{
    ownSender(event);
    // Only save the reviewed bundled template, never caller-provided content.
    const result=await dialog.showSaveDialog(win,{title:'保存 System Template',defaultPath:'literature-workspace.rn-system.json',filters:[{name:'Research Nexus System Template',extensions:['json']}]});
    if(result.canceled)return false;
    fs.copyFileSync(path.join(root,'system-templates','literature-workspace.rn-system.json'),result.filePath);return true;
  });
  ipcMain.handle('open-setup-link',(event,key)=>{
    ownSender(event);
    const links={'zotero-download':'https://www.zotero.org/download/', 'orx-download':'https://github.com/alphaXiv/OpenResearch#readme','drive-download':'https://support.google.com/drive/answer/10838124','git-download':'https://git-scm.com/downloads/win'};
    if(!Object.hasOwn(links,key))throw Error('不支持的安装入口。');
    return shell.openExternal(links[key]);
  });
  ipcMain.handle('open-designer-node',async(event,id)=>{
    ownSender(event);if(typeof id!=='string'||!/^[-a-zA-Z0-9_]{1,64}$/.test(id))throw new Error('工具编号无效。');
    const data=await fetch(origin+'/api/designer').then(r=>r.json());
    const node=data.project.nodes.find(n=>n.id===id);if(!node)throw new Error('此工具已被移除。');
    if(node.builtin)throw new Error('请从内置工具入口打开此应用。');
    if(node.kind==='website') {
      const key='custom-'+id,previous=customTools.get(key);customTools.set(key,{url:node.url,name:node.name});
      if(previous?.url===node.url&&views.has(key)){activeTool=key;layout();views.get(key).webContents.focus();}
      else await showTool(key,node.url);
      return {tool:key,name:node.name,url:views.get(key).webContents.getURL()||node.url};
    }
    if(node.kind==='app') {
      if(!path.isAbsolute(node.executable||'')||path.extname(node.executable).toLowerCase()!=='.exe'||!fs.statSync(node.executable).isFile())throw new Error('请选择已安装应用的 .exe 文件。');
      const child=spawn(node.executable,[],{detached:true,stdio:'ignore',windowsHide:false});
      await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});child.unref();return {launched:true};
    }
    const folder=path.join(root,'data','designer','outputs',id);fs.mkdirSync(folder,{recursive:true});
    const error=await shell.openPath(folder);if(error)throw new Error(error);return {opened:true};
  });
  await win.loadURL(address);
  workspaceReady=true;
  if(systemsRequested){systemsRequested=false;win.webContents.send('open-systems');}
  if(designerRequested){designerRequested=false;openResearchRequested=false;win.webContents.send('open-designer');}
  // Warm the last alphaXiv page without delaying the dashboard or selecting it.
  if(!smoke) {webTools.prewarmAlpha();layout();}
  if(!smoke && openResearchRequested) {
    openResearchRequested=false;
    try {await launchOpenResearch();}
    catch(e) {activeTool=null;layout();win.webContents.send('native-tool-state',{event:'error',tool:'openresearch',message:e.message});}
  }
  if (!smoke) { try { fs.unlinkSync(path.join(root,'data','startup-error.txt')); } catch {} }
  if(process.argv.includes('--verify-native-tools')) {
    await require('./verify-native-tools.cjs')({root,win,nativeApps,showNativeTool,layout});
    if(process.argv.includes('--quit-after-native-check'))app.quit();
  }
  if(process.argv.includes('--verify-diy-live')) {
    try {await require('./verify-diy-live.cjs')({root,win,origin});}
    catch(e){dialog.showErrorBox('DIY 实际测试未完成',e.message);}
  }
  if (smoke) {
    await win.webContents.executeJavaScript(`new Promise((resolve,reject)=>{const started=Date.now();const check=()=>{if(document.querySelector('main h1'))resolve(true);else if(Date.now()-started>10000)reject(new Error('Dashboard did not render'));else setTimeout(check,50)};check()})`);
    const state=await win.webContents.executeJavaScript('document.title');
    if (!smokeFullscreen) {
      const image=await win.webContents.capturePage();
      fs.writeFileSync(path.join(root,'data','desktop-smoke.png'),image.toPNG());
    }
    fs.writeFileSync(path.join(root,'data','desktop-smoke.json'),JSON.stringify({title:state,origin,preload:await win.webContents.executeJavaScript('typeof window.workspace?.showTool'),ok:true}));
    if (smokeFullscreen) {
      const assert = require('node:assert/strict');
      const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
      const cfg = (await (await fetch(origin+'/api/status')).json()).config;
      showWorkspace();
      const results = [];
      for (const [tool, url] of [['alpha','https://www.alphaxiv.org/']]) {
        await showTool(tool,url);
        const view=views.get(tool), started=Date.now();
        while (view.webContents.isLoading() && Date.now()-started<20000) await delay(100);
        const beforeURL=view.webContents.getURL(), beforeBounds=view.getBounds();
        view.webContents.focus();
        view.webContents.sendInputEvent({type:'keyDown',keyCode:'F11'});
        view.webContents.sendInputEvent({type:'keyUp',keyCode:'F11'});
        await delay(500);
        assert.equal(win.isFullScreen(),true,tool+' enters fullscreen from embedded focus');
        const [width,height]=win.getContentSize();
        assert.deepEqual(view.getBounds(),{x:0,y:0,width,height});
        view.webContents.sendInputEvent({type:'keyDown',keyCode:'F11'});
        view.webContents.sendInputEvent({type:'keyUp',keyCode:'F11'});
        await delay(500);
        assert.equal(win.isFullScreen(),false,tool+' leaves fullscreen');
        assert.equal(view.getBounds().x,236); assert.equal(view.getBounds().y,56);
        assert.equal(view.webContents.getURL(),beforeURL,'Fullscreen keeps the loaded page');
        results.push({tool,enter_exit_f11:true,fills_screen:true,restored_chrome:true,page_preserved:true,beforeBounds});
      }
      activeTool=null; layout(); win.webContents.focus();
      win.webContents.sendInputEvent({type:'keyDown',keyCode:'F11'});
      win.webContents.sendInputEvent({type:'keyUp',keyCode:'F11'});
      await delay(400); assert.equal(win.isFullScreen(),true);
      win.webContents.sendInputEvent({type:'keyDown',keyCode:'F11'});
      win.webContents.sendInputEvent({type:'keyUp',keyCode:'F11'});
      await delay(400); assert.equal(win.isFullScreen(),false);
      fs.writeFileSync(path.join(root,'data','fullscreen-smoke.json'),JSON.stringify({passed:true,results,dashboard_f11:true,borrowed_backend:true},null,2));
      app.quit(); return;
    }
    if (smokeTray) {
      const assert = require('node:assert/strict');
      const before = await (await fetch(origin+'/api/status')).json();
      showWorkspace();
      win.close();
      assert.equal(win.isDestroyed(),false,'Closing the window must retain it');
      assert.equal(win.isVisible(),false,'Closing the window must hide it');
      const after = await (await fetch(origin+'/api/status')).json();
      assert.equal(after.config.auto_sync,before.config.auto_sync);
      assert.equal(after.config.sync_interval_seconds,before.config.sync_interval_seconds);
      trayMenu.getMenuItemById('show-workspace').click();
      assert.equal(win.isVisible(),true,'Tray Open must restore the window');
      win.minimize();
      await new Promise(resolve=>setTimeout(resolve,200));
      showWorkspace();
      await new Promise(resolve=>setTimeout(resolve,200));
      assert.equal(win.isMinimized(),false,'Tray Open must restore a minimized window');
      const report={passed:true,close_hides_window:true,backend_alive_after_close:true,
        tray_open_restores:true,minimized_window_restores:true,quit_menu_requested:true,
        auto_sync:after.config.auto_sync,interval_seconds:after.config.sync_interval_seconds,
        backend_pid:backend.pid,url:origin};
      fs.writeFileSync(path.join(root,'data','tray-smoke.json'),JSON.stringify(report,null,2));
      trayMenu.getMenuItemById('quit-workspace').click();
      return;
    }
    if(smokeTools) {
      const results=[];
      for(const [tool,address] of [['alpha','https://www.alphaxiv.org/'],['zotero','https://www.zotero.org/mylibrary']]) {
        await showTool(tool,address);
        const view=views.get(tool),started=Date.now();
        while(view.webContents.isLoading() && Date.now()-started<30000)await new Promise(r=>setTimeout(r,200));
        results.push({tool,url:view.webContents.getURL(),title:view.webContents.getTitle(),preferences:{nodeIntegration:view.webContents.getLastWebPreferences().nodeIntegration,sandbox:view.webContents.getLastWebPreferences().sandbox}});
      }
      const csrfHeaders={Origin:origin,'Content-Type':'application/json','X-CSRF-Token':serverCSRF};
      await fetch(origin+'/api/start-openresearch',{method:'POST',headers:csrfHeaders,body:'{}'});
      let orx;
      for(let i=0;i<30;i++) {orx=await(await fetch(origin+'/api/openresearch')).json();if(orx.ready)break;await new Promise(r=>setTimeout(r,1000));}
      if(!orx?.ready)throw new Error('OpenResearch dashboard did not start');
      await showTool('openresearch',orx.url);
      const view=views.get('openresearch'),started=Date.now();
      while(view.webContents.isLoading() && Date.now()-started<15000)await new Promise(r=>setTimeout(r,100));
      results.push({tool:'openresearch',url:view.webContents.getURL(),title:view.webContents.getTitle(),ready:orx.ready});
      activeTool=null;layout();
      fs.writeFileSync(path.join(root,'data','desktop-tools-check.json'),JSON.stringify({results,singleWindow:BrowserWindow.getAllWindows().length===1},null,2));
    }
    app.quit();
  }
}
app.on('window-all-closed',()=>{if(!trayIcon || trayIcon.isDestroyed() || shuttingDown)app.quit();});
app.on('before-quit',event=>quitGuard.handle(event));
async function shutdown() {
    await webTools?.checkpoint();
    await nativeApps?.detach();
    webTools?.stop();
    if(backend && origin && serverCSRF) {
      try {await fetch(origin+'/api/shutdown',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json','X-CSRF-Token':serverCSRF},body:'{}',signal:AbortSignal.timeout(3000)});}catch{}
      if(backend && backend.exitCode===null) await Promise.race([new Promise(resolve=>backend.once('exit',resolve)),new Promise(resolve=>setTimeout(resolve,3500))]);
    }
    if(backend && backend.exitCode===null)backend.kill();
    if(backendLog!==undefined) {try {fs.closeSync(backendLog);}catch{}}
    if(trayIcon && !trayIcon.isDestroyed())trayIcon.destroy();
}
