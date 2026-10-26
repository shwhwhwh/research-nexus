// Apply before the stylesheet. Electron nativeTheme updates this media query.
(() => {
  const media=matchMedia('(prefers-color-scheme: dark)');
  const apply=dark=>document.documentElement.dataset.theme=dark?'dark':'light';
  apply(media.matches);
  media.addEventListener('change',event=>apply(event.matches));
})();
