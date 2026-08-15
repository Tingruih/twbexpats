/**
 * katex-lazy.js — KaTeX 閒置時背景預抓
 * 載入於：player_detail.j2（只有球員詳細頁的 tooltip 會用到公式）
 *
 * 作用：頁面 load 完成後，用 requestIdleCallback（不支援時退化為 setTimeout）
 *       在瀏覽器閒置時才把 KaTeX 的 CSS/JS 插進 <head>，
 *       不阻塞首屏渲染，首頁 / retired / 404 也完全不會下載 KaTeX。
 *
 * 若使用者在載入完成前就 hover 公式欄位，stats-tooltip.js 會退回顯示純文字公式
 * （window.katex 尚未存在時的既有 fallback），KaTeX 到位後的下一次 hover 即正常渲染。
 */
(function () {
    'use strict';

    var VERSION = '0.16.11';
    var CSS_URL = 'https://cdn.jsdelivr.net/npm/katex@' + VERSION + '/dist/katex.min.css';
    var JS_URL = 'https://cdn.jsdelivr.net/npm/katex@' + VERSION + '/dist/katex.min.js';
    var started = false;

    function loadKatex() {
        if (started) return;
        started = true;

        var css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = CSS_URL;
        document.head.appendChild(css);

        var js = document.createElement('script');
        js.src = JS_URL;
        js.async = true;
        document.head.appendChild(js);
    }

    function schedule() {
        if (typeof window.requestIdleCallback === 'function') {
            // timeout：即使一直沒有閒置空檔，最晚 3 秒後也會載入
            window.requestIdleCallback(loadKatex, { timeout: 3000 });
        } else {
            window.setTimeout(loadKatex, 1200);
        }
    }

    if (document.readyState === 'complete') {
        schedule();
    } else {
        window.addEventListener('load', schedule);
    }
})();
