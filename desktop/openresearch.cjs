// Compatibility entry for older shortcuts: reuse the single RB workspace.
const { app } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
app.whenReady().then(() => {
  const background=process.argv.includes('--background');
  const child = spawn(background?path.join(__dirname,'NativeDockHost.exe'):process.execPath,background?[]:[path.resolve(__dirname,'..'),'--open-openresearch'],
    { cwd: path.resolve(__dirname, '..'), windowsHide: true, detached: true, stdio: 'ignore' });
  child.on('error', () => app.exit(1)); child.unref(); app.quit();
});
