// Runs in an isolated renderer world. Only URL and scroll offsets leave the page.
function installReadingPosition(saved) {
  if (globalThis.nexusReadingPosition) return;
  let url = location.href, restoring = false, cancelled = false;
  const targets = new Map();
  const root = () => document.scrollingElement;
  function selector(element) {
    if (element === root() || element === document) return '@document';
    if (!(element instanceof Element)) return null;
    if (element.id) return '#' + CSS.escape(element.id);
    const parts = [];
    for (let node = element; node && parts.length < 16; node = node.parentElement) {
      if (node.id) { parts.unshift('#' + CSS.escape(node.id)); break; }
      let index = 1;
      for (let sibling = node.previousElementSibling; sibling; sibling = sibling.previousElementSibling)
        if (sibling.tagName === node.tagName) index++;
      parts.unshift(node.localName + ':nth-of-type(' + index + ')');
    }
    return parts.join(' > ');
  }
  function remember(element) {
    if (location.href !== url) { url = location.href; targets.clear(); }
    const key = selector(element);
    if (key) {
      if (targets.size >= 32 && !targets.has(key)) targets.delete(targets.keys().next().value);
      targets.set(key, element === document ? root() : element);
    }
  }
  document.addEventListener('scroll', event => remember(event.target), {capture: true, passive: true});
  for (const type of ['wheel', 'touchstart', 'pointerdown', 'keydown'])
    document.addEventListener(type, event => { if (event.isTrusted) cancelled = true; }, {capture: true, passive: true});
  globalThis.nexusReadingPosition = () => {
    if (location.href !== url) { url = location.href; targets.clear(); }
    // Chromium may coalesce scroll events for offscreen or hidden containers.
    // Sample nonzero offsets at checkpoint time as well as tracking events.
    for (const element of document.querySelectorAll('*'))
      if (element.scrollTop || element.scrollLeft) remember(element);
    remember(root());
    return {url, restoring, entries: [...targets].filter(([,node]) => node?.isConnected).map(([selector,node]) =>
      ({selector, x: node.scrollLeft, y: node.scrollTop})).slice(0, 32)};
  };
  // Include containers whose browser-managed position was restored before our listener.
  for (const element of document.querySelectorAll('*'))
    if (element.scrollTop || element.scrollLeft) remember(element);
  if (saved?.url !== location.href || !saved.entries?.length) return;
  restoring = true;
  const started = Date.now();
  let stable = 0, retry;
  const observer = new MutationObserver(() => restore());
  observer.observe(document.documentElement, {childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'src']});
  document.addEventListener('load', restore, true);
  function finish() {
    restoring = false; clearTimeout(retry); observer.disconnect(); document.removeEventListener('load', restore, true);
  }
  function restore() {
    if (!restoring) return;
    clearTimeout(retry);
    if (cancelled || location.href !== saved.url || Date.now() - started > 12000) { finish(); return; }
    let complete = true;
    for (const entry of saved.entries) {
      let node;
      try { node = entry.selector === '@document' ? root() : document.querySelector(entry.selector); } catch {}
      if (!node || node.scrollHeight - node.clientHeight < entry.y - 2 || node.scrollWidth - node.clientWidth < entry.x - 2) {
        complete = false; continue;
      }
      if (Math.abs(node.scrollTop - entry.y) > 1 || Math.abs(node.scrollLeft - entry.x) > 1)
        node.scrollTo({left: entry.x, top: entry.y, behavior: 'instant'});
      remember(node);
    }
    stable = complete ? stable + 1 : 0;
    if (stable >= 5) { finish(); return; }
    retry = setTimeout(restore, 100);
  }
  restore();
}

module.exports = {installReadingPosition};
