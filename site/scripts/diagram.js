/* 架构图：把每条连线的实际路径长度写进 --len，进入视口后加 .is-drawn，
   由 CSS 负责连线生长、节点点亮和光点流动。 */

window.Maestro = window.Maestro || {};

window.Maestro.diagram = (function () {
  'use strict';

  function init() {
    var diagram = document.getElementById('diagram');
    if (!diagram) return;

    measure(diagram);

    // 复用 reveal 的视口判定（含后台标签页的兜底扫描）
    var reveal = window.Maestro.reveal;
    if (reveal && typeof reveal.watch === 'function') {
      reveal.watch(diagram, function (el) {
        el.classList.add('is-drawn');
      });
    } else {
      diagram.classList.add('is-drawn');
    }
  }

  /* 生长动画要求 dasharray 恰好等于路径长度，否则会提前画完或画不满 */
  function measure(diagram) {
    var lines = diagram.querySelectorAll('.dg-line');

    Array.prototype.forEach.call(lines, function (path) {
      // 虚线样式的总线与刻度不做生长，保持自身 dasharray
      if (path.classList.contains('dg-line--bus') || path.classList.contains('dg-line--tick')) {
        return;
      }

      var length;
      try {
        length = path.getTotalLength();
      } catch (err) {
        return; // 极老的浏览器拿不到长度，退回 CSS 里的默认值
      }

      // 多留 1px，避免亚像素舍入在末端留下缺口
      path.style.setProperty('--len', Math.ceil(length) + 1);
    });
  }

  return { init: init };
})();
