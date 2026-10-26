// Real Electron integration test, with an isolated profile and local HTTPS fixtures.
const {app, BrowserWindow, session} = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {ToolViews, restorableAlphaURL} = require('./tool-views.cjs');
const root = path.resolve(__dirname, '..');
const testRoot = path.join(root, 'data', 'alpha-switch-test');
app.setPath('userData', path.join(testRoot, 'profile'));
app.on('window-all-closed',()=>{}); // Recreate the window to exercise restart restoration.
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let win, cache;
async function waitFor(predicate, message, timeout = 7000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { if (await predicate()) return; } catch {}
    await delay(50);
  }
  throw Error(message);
}
function fixture() {
  return `<!doctype html><html><head><style>
    body {margin:0;height:7000px} #reader {height:320px;overflow:auto;width:90%}
    @media(max-width:100px){#reader{height:1px}}
  </style></head><body><h1>Reading fixture</h1><input id="draft">
  <div id="reader"><div id="pages"></div></div><div style="height:6000px"></div>
  <script>
    globalThis.documentInstance = Math.random().toString(36);
    addEventListener('resize',()=>{if(innerWidth<=100){document.querySelector('#reader').scrollTop=0;scrollTo(0,0);}});
    setTimeout(()=>{document.querySelector('#pages').style.height='6000px';},600);
  </script></body></html>`;
}
function makeCache(stateFile) {
  win = new BrowserWindow({show:false,width:1440,height:940,webPreferences:{sandbox:true,nodeIntegration:false,contextIsolation:true}});
  const bounds = {x:236,y:56,width:1204,height:884};
  cache = new ToolViews({win,root,stateFile,
    isAllowed: (tool,url) => tool==='alpha' && restorableAlphaURL(url),
    safeWebNavigation: url => /^https?:/.test(url),
    onCreate: () => cache.layout(bounds, null, true)
  });
  return bounds;
}
async function closeCache() {
  await cache.checkpoint(); cache.stop();
  for (const view of cache.views.values()) if (!view.webContents.isDestroyed()) view.webContents.close();
  win.destroy();
}
app.whenReady().then(async () => {
  fs.mkdirSync(testRoot,{recursive:true});
  const stateFile=path.join(testRoot,'state.json');
  fs.writeFileSync(stateFile,JSON.stringify({version:1}));
  let requests=0;
  const profile=session.fromPartition('persist:research-alpha');
  profile.protocol.handle('https',async request=>{
    if(new URL(request.url).pathname==='/favicon.ico')return new Response(null,{status:204});
    requests++;
    await delay(250);
    return new Response(fixture(),{headers:{'Content-Type':'text/html','Cache-Control':'no-store'}});
  });
  const bounds=makeCache(stateFile);
  cache.prewarmAlpha();
  const firstView=cache.views.get('alpha'),wc=firstView.webContents;
  for(let i=0;i<5;i++)cache.open('alpha');
  await cache.records.get('alpha').loading;
  await waitFor(()=>wc.executeJavaScript("document.querySelector('#pages')?.offsetHeight===6000"),'Fixture did not become ready');
  assert.equal(requests,1,'Concurrent sidebar clicks must share the prewarm request');
  const security=wc.getLastWebPreferences();
  assert.equal(security.nodeIntegration,false);assert.equal(security.sandbox,true);assert.equal(security.contextIsolation,true);
  cache.layout(bounds,'alpha',true);
  const instance=await wc.executeJavaScript(`document.querySelector('#draft').value='unsent note';
    history.pushState({},'', '/abs/2601.00001');scrollTo(0,1500);document.querySelector('#reader').scrollTop=2340;documentInstance`);
  await delay(150);
  await cache.checkpoint();
  const historyBefore=wc.navigationHistory.getAllEntries();
  const timings=[];
  for(let i=0;i<8;i++) {
    cache.layout(bounds,i%2?'zotero':'openresearch',true);
    assert.deepEqual(firstView.getBounds(),bounds,'Hidden views retain their viewport');
    assert.equal(firstView.getVisible(),false);
    await delay(30);
    const started=performance.now();
    cache.open('alpha');cache.layout(bounds,'alpha',true);
    timings.push(performance.now()-started);
    await delay(30);
  }
  const kept=await wc.executeJavaScript(`({instance:documentInstance,draft:document.querySelector('#draft').value,
    y:scrollY,reader:document.querySelector('#reader').scrollTop,width:innerWidth,url:location.href})`);
  assert.equal(kept.instance,instance);assert.equal(kept.draft,'unsent note');
  assert.equal(kept.y,1500);assert.equal(kept.reader,2340);assert.equal(kept.width,bounds.width);
  assert.equal(kept.url,'https://www.alphaxiv.org/abs/2601.00001');assert.equal(requests,1);
  assert.deepEqual(wc.navigationHistory.getAllEntries(),historyBefore,'SPA navigation history survives switching');
  cache.layout({x:0,y:0,width:1440,height:940},'alpha',true);
  cache.layout(bounds,'alpha',true);
  assert.equal(wc.getURL(),kept.url);
  cache.layout(bounds,'alpha',false);assert.equal(wc.getBackgroundThrottling(),true);
  cache.layout(bounds,'alpha',true);assert.equal(wc.getBackgroundThrottling(),false);
  cache.open('alpha','https://www.alphaxiv.org/abs/2602.00002');
  for(let i=0;i<5;i++){cache.open('alpha');cache.open('alpha','https://www.alphaxiv.org/abs/2602.00002');}
  await cache.records.get('alpha').loading;
  await waitFor(()=>wc.executeJavaScript("document.querySelector('#pages')?.offsetHeight===6000"),'Second paper did not load');
  assert.equal(requests,2,'An explicit new paper loads once; repeat clicks do not abort it');
  assert.equal(wc.navigationHistory.canGoBack(),true,'Back remains available after opening another paper');
  await wc.executeJavaScript("scrollTo(0,1700);document.querySelector('#reader').scrollTop=2800");
  await delay(100);
  await cache.checkpoint();
  const saved=JSON.parse(fs.readFileSync(stateFile,'utf8'));
  assert.equal(saved.alpha.url,'https://www.alphaxiv.org/abs/2602.00002');
  assert(saved.alpha.position.entries.some(entry=>entry.selector==='#reader'&&entry.y===2800));
  await closeCache();
  makeCache(stateFile);cache.prewarmAlpha();
  const restarted=cache.views.get('alpha').webContents;
  await cache.records.get('alpha').loading;
  cache.open('alpha');cache.layout(bounds,'alpha',true);
  try {
    await waitFor(()=>restarted.executeJavaScript("scrollY===1700&&document.querySelector('#reader')?.scrollTop===2800"),'Restart did not restore document and delayed reader positions');
  } catch(error) {
    console.log(JSON.stringify({saved,record:cache.records.get('alpha').restore,
      page:await restarted.executeJavaScript("({url:location.href,y:scrollY,reader:document.querySelector('#reader')?.scrollTop,height:document.querySelector('#pages')?.offsetHeight,visibility:document.visibilityState,clientHeight:document.querySelector('#reader')?.clientHeight,scrollHeight:document.querySelector('#reader')?.scrollHeight,scrollWidth:document.querySelector('#reader')?.scrollWidth,clientWidth:document.querySelector('#reader')?.clientWidth})"),
      tracker:await restarted.executeJavaScriptInIsolatedWorld(1001,[{code:'globalThis.nexusReadingPosition?.()'}])}));
    throw error;
  }
  await delay(600);await cache.checkpoint();
  assert.equal(restarted.getURL(),saved.alpha.url);assert.equal(requests,3);
  const resumed=await restarted.executeJavaScript("({url:location.href,y:scrollY,reader:document.querySelector('#reader').scrollTop})");
  for(const url of ['https://accounts.google.com/login','https://www.alphaxiv.org/auth/callback?code=private','https://www.alphaxiv.org/?access_token=private','javascript:alert(1)'])
    assert.equal(restorableAlphaURL(url),false,'Authentication and unsafe URLs must not be persisted');
  const report={passed:true,isolated_profile:true,network_fixture:true,live_accounts_untouched:true,
    switches:8,network_requests_during_switches:0,same_document:true,draft_preserved:true,
    document_scroll_preserved:1500,nested_scroll_preserved:2340,history_preserved:true,
    concurrent_initial_load_requests:1,explicit_paper_requests:1,fullscreen_keeps_page:true,
    background_throttling_on_hide:true,restart_restores_delayed_content:resumed,
    switch_dispatch_ms:timings.map(value=>Number(value.toFixed(2))),authentication_urls_excluded:true};
  fs.writeFileSync(path.join(root,'data','alpha-switch-acceptance.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  await closeCache();app.quit();
}).catch(error=>{
  fs.mkdirSync(testRoot,{recursive:true});
  fs.writeFileSync(path.join(testRoot,'error.txt'),error.stack||String(error));
  console.error(error);cache?.stop();if(win&&!win.isDestroyed())win.destroy();app.exit(1);
});
