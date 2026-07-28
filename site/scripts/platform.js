/* 下载区：识别访客系统，把对应平台卡片标为推荐。
   识别不出来时两张卡片都保持中性，不猜。 */

window.Maestro = window.Maestro || {};

window.Maestro.platform = (function () {
  'use strict';

  function init() {
    var grid = document.getElementById('downloadGrid');
    if (!grid) return;

    var current = detect();
    if (!current) return;

    var card = grid.querySelector('[data-platform="' + current + '"]');
    if (card) card.classList.add('is-recommended');
  }

  function detect() {
    // userAgentData 更可靠，但目前只有 Chromium 系提供
    var hinted = navigator.userAgentData && navigator.userAgentData.platform;
    var raw = String(hinted || navigator.platform || navigator.userAgent || '').toLowerCase();

    // iPadOS 会伪装成 macOS，但它装不了桌面端，不作推荐
    if (navigator.maxTouchPoints > 1 && /mac/.test(raw)) return null;

    if (/mac|darwin/.test(raw)) return 'mac';
    if (/win/.test(raw)) return 'win';
    return null;
  }

  return { init: init };
})();
