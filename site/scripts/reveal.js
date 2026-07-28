/* 滚动揭示：元素进入视口后加 .is-visible，错开延迟写在 HTML 的 --reveal-delay 上。
   同时对外提供 watch()，让架构图之类的模块复用同一套「进入视口」判定。 */

window.Maestro = window.Maestro || {};

window.Maestro.reveal = (function () {
  'use strict';

  var BOTTOM_MARGIN = 0.12; // 底部留出一段，元素露头就揭示，不必等整块进来
  var watched = []; // 尚未触发的目标，用于兜底扫描

  function init() {
    var targets = document.querySelectorAll('.reveal');

    Array.prototype.forEach.call(targets, function (el) {
      watch(el, function (target) {
        target.classList.add('is-visible');
      });
    });

    // 标签页在后台时浏览器会停发 IntersectionObserver 回调；
    // 切回来补扫一次，避免用户看到一片空白。
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) sweep();
    });

    window.addEventListener('load', sweep);
  }

  /* 注册一个目标：进入视口时调用 onEnter，只调用一次 */
  function watch(el, onEnter) {
    if (!el || typeof onEnter !== 'function') return;

    var entry = { el: el, onEnter: onEnter, done: false };
    watched.push(entry);

    if (!('IntersectionObserver' in window)) {
      fire(entry);
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (record) {
          if (record.isIntersecting) {
            fire(entry);
            observer.disconnect();
          }
        });
      },
      { rootMargin: '0px 0px -' + BOTTOM_MARGIN * 100 + '% 0px', threshold: 0.12 }
    );

    observer.observe(el);
  }

  function fire(entry) {
    if (entry.done) return;
    entry.done = true;
    entry.onEnter(entry.el);
  }

  /* 兜底：按几何位置判断谁已经在视口内，触发过的自然被跳过 */
  function sweep() {
    var limit = window.innerHeight * (1 - BOTTOM_MARGIN);

    watched = watched.filter(function (entry) {
      if (entry.done) return false;

      var rect = entry.el.getBoundingClientRect();
      if (rect.top < limit && rect.bottom > 0) {
        fire(entry);
        return false;
      }
      return true;
    });
  }

  return { init: init, watch: watch };
})();
