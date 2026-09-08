(function () {
  'use strict';
  if (window.__siteVisitsStarted) return;
  window.__siteVisitsStarted = true;
  var panel = document.querySelector('[data-site-visits]');
  var status = panel && panel.querySelector('[data-visits-status]');
  if (location.hostname !== 'jademath.github.io') {
    if (status) status.textContent = 'Visitor statistics are available on the published website.';
    return;
  }
  if (navigator.doNotTrack === '1' || window.doNotTrack === '1') {
    if (status) status.textContent = 'Do Not Track is enabled. Open the map below to view statistics.';
    return;
  }
  var slot = panel ? panel.querySelector('[data-visits-map]') : document.querySelector('[data-visits-compact]');
  if (!slot) return;
  var link = document.createElement('a');
  link.href = 'https://s01.flagcounter.com/more/rXB/';
  link.setAttribute('aria-label', 'View site visitor statistics on Flag Counter');
  var image = document.createElement('img');
  image.alt = panel ? 'World visitor map with country flags, visitor total, and page views' : 'Site page views — Flag Counter';
  image.decoding = 'async';
  image.style.border = '0';
  image.style.maxWidth = '100%';
  image.style.height = 'auto';
  image.style.verticalAlign = 'middle';
  var timer = setTimeout(function () {
    if (status) status.textContent = 'The map is taking longer to load. You can open the country statistics below.';
  }, 12000);
  image.onload = function () { clearTimeout(timer); if (status) status.hidden = true; };
  image.onerror = function () {
    clearTimeout(timer);
    link.remove();
    if (status) status.textContent = 'Visitor map temporarily unavailable. Open the country statistics below.';
  };
  link.appendChild(image);
  slot.appendChild(link);
  // Exactly one visible, linked counter per document; the full map and mini
  // counter share the same ID, so all pages contribute to the same totals.
  image.src = panel
    ? 'https://s01.flagcounter.com/map/rXB/size_l/txt_243B48/border_FFFFFF/pageviews_1/viewers_0/flags_0/'
    : 'https://s01.flagcounter.com/mini/rXB/bg_FFFFFF/txt_526577/border_FFFFFF/flags_0/';
}());
