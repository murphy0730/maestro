/* 顶栏：滚动态、当前区块高亮、移动端菜单开关。
   （平滑滚动交给 CSS 的 scroll-behavior，减弱动态效果时会自动退回瞬移） */

window.Maestro = window.Maestro || {};

window.Maestro.nav = (function () {
  'use strict';

  var STUCK_AT = 80;

  function init() {
    var nav = document.getElementById('nav');
    var menu = document.getElementById('navMenu');
    var toggle = document.getElementById('navToggle');
    if (!nav || !menu || !toggle) return;

    var links = Array.prototype.slice.call(menu.querySelectorAll('.nav__link'));

    // 菜单顺序（下载/简介/社区/文档）和页面顺序不一致，
    // 判定当前区块必须按页面位置排序，否则高亮会错位。
    var spots = links
      .map(function (link) {
        var id = link.getAttribute('href');
        var section = id && id.charAt(0) === '#' ? document.querySelector(id) : null;
        return section ? { link: link, section: section } : null;
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return a.section.offsetTop - b.section.offsetTop;
      });

    setupStuck(nav);
    setupSpy(links, spots);
    setupToggle(menu, toggle);
  }

  /* 滚过阈值后顶栏切换为磨砂玻璃 */
  function setupStuck(nav) {
    var ticking = false;

    function apply() {
      nav.classList.toggle('is-stuck', window.scrollY > STUCK_AT);
      ticking = false;
    }

    window.addEventListener(
      'scroll',
      function () {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(apply);
      },
      { passive: true }
    );

    apply();
  }

  /* 以视口上三分之一处为判定线，选中最后一个已越过该线的区块 */
  function setupSpy(links, spots) {
    if (!spots.length) return;

    var ticking = false;

    function apply() {
      var line = window.scrollY + window.innerHeight * 0.34;
      var active = null;

      for (var i = 0; i < spots.length; i++) {
        if (spots[i].section.offsetTop <= line) active = spots[i].link;
      }

      // 滚到底部时强制选中最后一个，避免尾部短区块永远高亮不到
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
        active = spots[spots.length - 1].link;
      }

      for (var j = 0; j < links.length; j++) {
        links[j].classList.toggle('is-active', links[j] === active);
      }

      ticking = false;
    }

    window.addEventListener(
      'scroll',
      function () {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(apply);
      },
      { passive: true }
    );

    window.addEventListener('resize', apply);
    apply();
  }

  /* 移动端汉堡菜单 */
  function setupToggle(menu, toggle) {
    function close() {
      menu.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', '展开菜单');
    }

    toggle.addEventListener('click', function () {
      var open = menu.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? '收起菜单' : '展开菜单');
    });

    // 点了任一菜单项就收起，否则面板会挡住刚跳到的区块
    menu.addEventListener('click', function (event) {
      if (event.target.closest('.nav__link')) close();
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') close();
    });

    window.addEventListener('resize', function () {
      if (window.innerWidth > 768) close();
    });
  }

  return { init: init };
})();
