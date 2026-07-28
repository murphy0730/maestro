/* 字标描线：入场播一次，悬停回放一次。
   动画本身在 CSS 里，这里只负责挂/重挂 .is-drawn。 */

window.Maestro = window.Maestro || {};

window.Maestro.brand = (function () {
  'use strict';

  function replay(brand) {
    // 同一帧内 remove + add 不会重启动画，中间必须强制一次重排
    brand.classList.remove('is-drawn');
    void brand.offsetWidth;
    brand.classList.add('is-drawn');
  }

  function init() {
    var brands = document.querySelectorAll('.brand');

    Array.prototype.forEach.call(brands, function (brand) {
      replay(brand);
      brand.addEventListener('mouseenter', function () {
        replay(brand);
      });
    });
  }

  return { init: init };
})();
