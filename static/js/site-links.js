(function () {
  var MANIFEST_PATH = '/static/data/links.json';

  function isExternal(url) {
    return /^https?:\/\//i.test(url);
  }

  function applyLinks(manifest) {
    var anchors = document.querySelectorAll('a[data-link-key]');
    anchors.forEach(function (anchor) {
      var key = anchor.getAttribute('data-link-key');
      if (!key || !manifest[key]) {
        return;
      }

      var url = manifest[key];
      anchor.setAttribute('href', url);
      if (isExternal(url)) {
        anchor.setAttribute('target', '_blank');
        anchor.setAttribute('rel', 'noopener noreferrer');
      }
    });
  }

  fetch(MANIFEST_PATH)
    .then(function (response) {
      if (!response.ok) {
        throw new Error('Failed to load links manifest');
      }
      return response.json();
    })
    .then(applyLinks)
    .catch(function (err) {
      console.warn('[site-links] ', err.message);
    });
})();
