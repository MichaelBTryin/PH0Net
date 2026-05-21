(function () {
  var key = 'ph0net_theme';
  var root = document.documentElement;
  var stored = localStorage.getItem(key);
  var prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
  var theme = stored || (prefersLight ? 'light' : 'dark');

  function apply(mode) {
    root.setAttribute('data-theme', mode);
    localStorage.setItem(key, mode);
    if (btn) btn.textContent = mode === 'dark' ? 'Light Mode' : 'Dark Mode';
  }

  var btn = document.createElement('button');
  btn.className = 'theme-toggle-btn';
  btn.type = 'button';
  btn.setAttribute('aria-label', 'Toggle theme');
  btn.addEventListener('click', function () {
    apply(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  });

  apply(theme);
  document.addEventListener('DOMContentLoaded', function () {
    document.body.appendChild(btn);
    apply(root.getAttribute('data-theme') || theme);
  });
})();
