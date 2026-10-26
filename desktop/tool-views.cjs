const {WebContentsView} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const {installReadingPosition} = require('./reading-position.cjs');
const READING_WORLD = 1001;
const ALPHA_HOME = 'https://www.alphaxiv.org/';

function restorableAlphaURL(address) {
  try {
    const url = new URL(address);
    return url.protocol === 'https:' && ['alphaxiv.org', 'www.alphaxiv.org'].includes(url.hostname)
      && !url.username && !url.password && !/^\/(?:api|auth|oauth|login|logout|signin|signout)(?:\/|$)/i.test(url.pathname)
      && ![...url.searchParams.keys()].some(key => /token|password|secret|session|auth|code|key/i.test(key));
  } catch { return false; }
}

function validPosition(position) {
  return position && restorableAlphaURL(position.url) && Array.isArray(position.entries)
    && position.entries.length <= 32 && position.entries.every(entry => typeof entry.selector === 'string'
      && entry.selector.length <= 2000 && Number.isFinite(entry.x) && entry.x >= 0 && entry.x <= 1e8
      && Number.isFinite(entry.y) && entry.y >= 0 && entry.y <= 1e8);
}

class ToolViews {
  constructor({win, root, views = new Map(), isAllowed, safeWebNavigation, bindFullscreenKeys = () => {}, onState = () => {}, onCreate = () => {}, stateFile}) {
    Object.assign(this, {win, root, views, isAllowed, safeWebNavigation, bindFullscreenKeys, onState, onCreate});
    this.stateFile = stateFile || path.join(root, 'data', 'web-tool-state.json');
    this.records = new Map();
    this.state = {version: 1};
    try {
      const saved = JSON.parse(fs.readFileSync(this.stateFile, 'utf8').replace(/^\uFEFF/, ''));
      if (restorableAlphaURL(saved.alpha?.url)) this.state.alpha = {
        url: saved.alpha.url,
        ...(validPosition(saved.alpha.position) ? {position: saved.alpha.position} : {})
      };
    } catch {}
    this.timer = setInterval(() => this.checkpoint(), 10000);
    this.timer.unref();
  }
  save() {
    try {
      fs.mkdirSync(path.dirname(this.stateFile), {recursive: true});
      fs.writeFileSync(this.stateFile + '.tmp', JSON.stringify(this.state, null, 2));
      fs.renameSync(this.stateFile + '.tmp', this.stateFile);
    } catch {} // A read-only disk must not break navigation.
  }
  rememberURL(address) {
    if (!restorableAlphaURL(address) || this.state.alpha?.url === address) return;
    const position = this.state.alpha?.position?.url === address ? this.state.alpha.position : undefined;
    this.state.alpha = {url: address, ...(position ? {position} : {})};
    this.save();
  }
  emit(tool, extra = {}) {
    const record = this.records.get(tool), wc = record?.view.webContents;
    if (!wc || wc.isDestroyed()) return;
    this.onState({tool, url: wc.getURL() || record.requestedURL, title: wc.getTitle(), loading: wc.isLoading(), ...extra});
  }
  ensure(tool) {
    if (this.views.has(tool)) return this.records.get(tool);
    const view = new WebContentsView({webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true,
      partition: tool === 'pdf' ? undefined : `persist:research-${tool}`, webSecurity: true,
      allowRunningInsecureContent: false, backgroundThrottling: tool !== 'alpha'}});
    const record = {view, started: false, requestedURL: '', crashed: false, failed: false, restore: null};
    this.views.set(tool, view); this.records.set(tool, record);
    view.setVisible(false);
    this.win.contentView.addChildView(view);
    this.bindFullscreenKeys(view.webContents);
    const wc = view.webContents;
    wc.setWindowOpenHandler(({url}) => {
      if (this.safeWebNavigation(url)) this.load(tool, url);
      return {action: 'deny'};
    });
    wc.on('will-navigate', (event, url) => { if (!this.safeWebNavigation(url)) event.preventDefault(); });
    const navigated = url => {
      record.requestedURL = url;
      if (tool === 'alpha') this.rememberURL(url);
      this.emit(tool);
    };
    wc.on('did-navigate', (_event,url) => navigated(url));
    wc.on('did-navigate-in-page', (_event,url,mainFrame) => { if(mainFrame)navigated(url); });
    wc.on('did-start-loading', () => this.emit(tool));
    wc.on('did-stop-loading', () => this.emit(tool));
    wc.on('did-finish-load', async () => {
      if (tool === 'alpha') {
        const position = record.restore?.url === wc.getURL() ? record.restore : null;
        record.restore = null;
        await wc.executeJavaScriptInIsolatedWorld(READING_WORLD, [{code: `(${installReadingPosition.toString()})(${JSON.stringify(position)})`}]).catch(() => {});
      }
      this.emit(tool);
    });
    wc.on('did-fail-load', (_event, code, description, url, mainFrame) => {
      if (mainFrame && code !== -3) {
        record.failed = true;
        this.emit(tool, {error: `页面未能加载：${description}`, url});
      }
    });
    wc.on('render-process-gone', () => {
      record.crashed = true;
      this.emit(tool, {error: '页面进程已停止，切回或刷新即可恢复上次阅读。'});
    });
    wc.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    wc.session.setPermissionCheckHandler(() => false);
    wc.session.on('will-download', (_event, item) => {
      const dir = path.join(this.root, 'data', 'downloads'); fs.mkdirSync(dir, {recursive: true});
      item.setSavePath(path.join(dir, `${Date.now()}-${path.basename(item.getFilename())}`));
    });
    this.onCreate();
    return record;
  }
  load(tool, address, restore = null) {
    const record = this.ensure(tool);
    record.started = true; record.requestedURL = address; record.crashed = false; record.failed = false; record.restore = restore;
    record.loading = record.view.webContents.loadURL(address).catch(() => {});
    return record;
  }
  open(tool, address) {
    const resume = tool === 'alpha' && !address;
    const target = address || (tool === 'alpha' ? this.state.alpha?.url || ALPHA_HOME : '');
    if (!this.isAllowed(tool, target)) throw new Error('Unsupported tool URL');
    let record = this.ensure(tool);
    // A request in flight counts as loaded: getURL() is still empty before commit.
    const current = record.requestedURL || record.view.webContents.getURL();
    if (!record.started || record.crashed || record.failed || (!resume && current !== target))
      record = this.load(tool, target, tool === 'alpha' && this.state.alpha?.position?.url === target ? this.state.alpha.position : null);
    this.emit(tool);
    return {ok: true, url: record.view.webContents.getURL() || record.requestedURL, loading: record.view.webContents.isLoading()};
  }
  prewarmAlpha() { this.open('alpha'); }
  layout(bounds, activeTool, windowVisible = true) {
    for (const [tool, view] of this.views) {
      // Hiding must never trigger a 1px responsive layout or reset a PDF reader.
      if (JSON.stringify(view.getBounds()) !== JSON.stringify(bounds)) view.setBounds(bounds);
      view.setVisible(tool === activeTool);
      if (tool === 'alpha' && view.webContents.getBackgroundThrottling() === windowVisible)
        view.webContents.setBackgroundThrottling(!windowVisible);
    }
  }
  async checkpoint() {
    const wc = this.views.get('alpha')?.webContents;
    if (!wc || wc.isDestroyed() || wc.isLoadingMainFrame()) return;
    try {
      const position = await Promise.race([
        wc.executeJavaScriptInIsolatedWorld(READING_WORLD, [{code: 'globalThis.nexusReadingPosition?.()'}]),
        new Promise(resolve => { const timer = setTimeout(() => resolve(null), 1000); timer.unref(); })
      ]);
      if (!position || position.restoring || position.url !== wc.getURL() || !validPosition(position)) return;
      this.state.alpha = {url: position.url, position: {url: position.url, entries: position.entries}};
      this.save();
    } catch {}
  }
  stop() { clearInterval(this.timer); }
}

module.exports = {ToolViews, restorableAlphaURL, validPosition};
