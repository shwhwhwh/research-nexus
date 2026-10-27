// Opt-in local integration check. Records window identity/geometry only, never
// screenshots, paper titles, account information, or research content.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
module.exports=async function verifyNativeTools({root,win,nativeApps,showNativeTool,layout}) {
  const file=path.join(root,'data','native-tools-check.json');
  let previous;try{previous=JSON.parse(fs.readFileSync(file,'utf8'));}catch{}
  const owner=win.getNativeWindowHandle().readBigUInt64LE().toString();
  async function until(predicate){
    const deadline=Date.now()+8000;
    do {const state=await nativeApps.status();if(predicate(state))return state;await new Promise(resolve=>setTimeout(resolve,100));}while(Date.now()<deadline);
    throw Error('Native window integration check timed out');
  }
  for(const tool of ['zotero','openresearch']) {
    await showNativeTool(tool);
    await until(state=>state.windows.some(w=>w.tool===tool&&w.child&&w.parent===owner&&w.visible));
  }
  const initial=await nativeApps.status();
  assert.equal(initial.windows.length,2);
  win.hide();layout();await until(s=>s.windows.every(w=>!w.visible));
  win.show();layout();await until(s=>s.windows.some(w=>w.tool==='openresearch'&&w.visible));
  win.setFullScreen(true);layout();
  await until(s=>s.windows.some(w=>w.tool==='openresearch'&&JSON.stringify(w.client)===JSON.stringify(s.viewport)));
  assert.equal(win.isFullScreen(),true);
  win.setFullScreen(false);layout();
  win.close();assert.equal(win.isDestroyed(),false);
  await until(s=>s.windows.every(w=>!w.visible));
  win.show();layout();
  for(const tool of ['zotero','openresearch'])await showNativeTool(tool);
  const final=await until(s=>s.windows.length===2&&s.windows.every(w=>w.child&&w.parent===owner));
  const identity=state=>state.windows.map(({tool,pid,hwnd})=>({tool,pid,hwnd})).sort((a,b)=>a.tool.localeCompare(b.tool));
  const windows=identity(final);
  assert.deepEqual(windows,identity(initial));
  const report={passed:true,embedded:true,hidePreservesWindows:true,closeGoesToTray:true,fullscreen:true,
    sameWindowsAfterSwitch:true,reusedAfterRestart:previous?.passed?JSON.stringify(previous.windows)===JSON.stringify(windows):null,windows};
  fs.writeFileSync(file,JSON.stringify(report,null,2));
  return report;
};
