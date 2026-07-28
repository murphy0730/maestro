/* 首屏：视频降级判定、滚动视差、标题逐字浮现、HUD 数据标签跳动 */

window.Maestro = window.Maestro || {};

window.Maestro.hero = (function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function init() {
    var hero = document.getElementById('hero');
    if (!hero) return;

    setupVideo(document.getElementById('heroMedia'), document.getElementById('heroVideo'));
    setupParallax(hero, document.getElementById('heroMedia'), document.getElementById('heroContent'));
    splitTitle(hero.querySelector('[data-split]'));
    setupHud(hero.querySelector('.hud'));
  }

  /* 窄屏、省流量、减弱动态效果或视频不可用时，一律退回静帧背景 */
  function setupVideo(media, video) {
    if (!media || !video) return;

    var conn = navigator.connection || navigator.webkitConnection;
    var frugal = !!(conn && (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || '')));

    if (window.innerWidth <= 768 || frugal || reduced) {
      fallback();
      return;
    }

    video.addEventListener('error', fallback);
    video.querySelectorAll('source').forEach(function (source) {
      source.addEventListener('error', function () {
        // 仅当所有候选源都失败时才降级
        if (video.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) fallback();
      });
    });

    // 某些浏览器会拒绝自动播放；静音状态下重试一次，仍失败就用静帧
    var attempt = video.play();
    if (attempt && typeof attempt.catch === 'function') {
      attempt.catch(function () {
        video.muted = true;
        var retry = video.play();
        if (retry && typeof retry.catch === 'function') retry.catch(fallback);
      });
    }

    function fallback() {
      media.classList.add('is-static');
      video.removeAttribute('autoplay');
      try {
        video.pause();
        video.removeAttribute('src');
        video.load();
      } catch (err) {
        /* 已经无法播放，静帧已生效，忽略 */
      }
    }
  }

  /* 视频随滚动缓慢下沉并加深遮蔽，内容层上移淡出 */
  function setupParallax(hero, media, content) {
    if (!media || !content || reduced) return;

    var ticking = false;

    function apply() {
      var height = hero.offsetHeight || window.innerHeight;
      var progress = Math.min(1, Math.max(0, window.scrollY / height));

      // 位移上限 1.5% 视口高。视频上下各溢出 2%，
      // 留出的 0.5% 裕度是防止亚像素舍入在边缘露出缝隙。
      media.style.setProperty('--parallax', (progress * height * 0.015).toFixed(1) + 'px');
      media.style.setProperty('--dim', progress.toFixed(3));

      content.style.setProperty('--lift', (-progress * 56).toFixed(1) + 'px');
      content.style.setProperty('--fade', Math.max(0, 1 - progress * 1.7).toFixed(3));

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

  /* 把标题拆成单字，逐字错开浮入；data-accent 指定的子串用主色点亮 */
  function splitTitle(title) {
    if (!title) return;

    var text = title.textContent;
    var accent = title.getAttribute('data-accent') || '';
    var accentStart = accent ? text.indexOf(accent) : -1;
    var accentEnd = accentStart >= 0 ? accentStart + accent.length : -1;

    var fragment = document.createDocumentFragment();
    for (var i = 0; i < text.length; i++) {
      var span = document.createElement('span');
      span.className = 'char';
      if (accentStart >= 0 && i >= accentStart && i < accentEnd) {
        span.className += ' char--accent';
      }
      span.style.setProperty('--ci', String(i));
      span.textContent = text.charAt(i);
      fragment.appendChild(span);
    }

    title.textContent = '';
    title.appendChild(fragment);
    title.classList.add('is-split');

    if (reduced) {
      title.classList.add('is-in');
      return;
    }

    function play() {
      title.classList.add('is-in');
    }

    // 隔两帧再触发，确保初始隐藏态已经上屏，动画不会被跳过
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(play);
    });

    // 后台标签页里 rAF 会被暂停，上面的回调可能永远轮不到，
    // 标题就一直停在透明态。补一个定时兜底，重复调用无副作用。
    window.setTimeout(play, 150);
  }

  /* HUD 数据标签：入场淡入，数值在基准附近轻微跳动，像实时读数 */
  function setupHud(hud) {
    if (!hud) return;

    hud.classList.add('is-live');
    if (reduced) return;

    var counters = Array.prototype.map.call(hud.querySelectorAll('[data-counter]'), function (el) {
      var base = parseFloat(el.getAttribute('data-counter'));
      var decimals = parseInt(el.getAttribute('data-decimals'), 10) || 0;
      return {
        el: el,
        base: base,
        decimals: decimals,
        // 抖动幅度按量级取，避免小数指标跳得像故障
        swing: decimals > 0 ? 0.3 : Math.max(1, Math.round(base * 0.04))
      };
    });

    if (!counters.length) return;

    setInterval(function () {
      if (document.hidden) return;
      var pick = counters[Math.floor(Math.random() * counters.length)];
      var delta = (Math.random() * 2 - 1) * pick.swing;
      pick.el.textContent = (pick.base + delta).toFixed(pick.decimals);
    }, 1600);
  }

  return { init: init };
})();
