/* 入口：按依赖无关的顺序启动各模块。
   单个模块出错不应连累其余部分，因此逐个捕获。 */

(function () {
  'use strict';

  var modules = ['nav', 'brand', 'reveal', 'hero', 'diagram', 'platform'];

  function start() {
    var registry = window.Maestro || {};

    modules.forEach(function (name) {
      var module = registry[name];
      if (!module || typeof module.init !== 'function') return;

      try {
        module.init();
      } catch (err) {
        // 某个特效挂了，页面内容仍应完整可读
        console.error('[Maestro] 模块 ' + name + ' 初始化失败：', err);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
