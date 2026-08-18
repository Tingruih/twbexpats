/**
 * player-search.js — 球員姓名搜尋（首頁 / 退休球員頁共用）
 * 載入於：index.j2, retired.j2
 *
 * 作用：
 *   1. 依輸入框內容即時過濾 #player-grid 內的球員卡片，
 *      比對卡片的 data-name（中文名 + 英文名），不分大小寫、部分符合。
 *      比對前會把空白與連字號正規化掉，讓 "hao yu" / "haoyu" 都能命中
 *      "李灝宇 Hao-Yu Lee"（羅馬拼音名幾乎都帶連字號）。
 *   2. 桌機用控制列內的底線輸入欄 (#player-search)，清除靠瀏覽器原生的叉叉；
 *      手機用放大鏡圓鈕 (#search-trigger) 切換控制列的「搜尋模式」
 *      （外層容器加上 .search-mode class，動畫效果由 CSS 處理），
 *      展開底線輸入框 (#player-search-mobile) 與取消鈕 (#search-cancel)。
 *      兩個輸入框內容互相同步。
 *
 * 無結果提示 (#search-empty-msg) 由模板預先渲染在 #player-grid 之外，
 * 這裡只負責填字與切換 hidden —— 放在 grid 內會被 index-sort.js 的 appendChild 重排。
 */
document.addEventListener("DOMContentLoaded", function () {
    var grid = document.getElementById("player-grid");
    var deskInput = document.getElementById("player-search");
    var inlineInput = document.getElementById("player-search-mobile");
    var trigger = document.getElementById("search-trigger");
    var cancelBtn = document.getElementById("search-cancel");
    var emptyMsg = document.getElementById("search-empty-msg");
    if (!grid || !deskInput) return;

    var inputs = [deskInput, inlineInput].filter(Boolean);

    // 空白、各式連字號／破折號、間隔號、句點、單引號一律去掉，
    // 讓「Po-Jung」「po jung」「pojung」在比對時視為同一串
    var SEPARATORS = /[\s'’.\-·・‐-―]+/g;

    function normalize(text) {
        return (text || "").toLowerCase().replace(SEPARATORS, "");
    }

    // 先算好每張卡片的正規化姓名，避免每次輸入都重算
    var entries = Array.from(grid.querySelectorAll(".player-card")).map(function (card) {
        return { card: card, name: normalize(card.dataset.name) };
    });

    /* ─── 卡片篩選 ─── */

    function filterCards(query) {
        var q = normalize(query);
        var visibleCount = 0;

        entries.forEach(function (entry) {
            var matches = q === "" || entry.name.indexOf(q) !== -1;
            entry.card.style.display = matches ? "" : "none";
            if (matches) visibleCount++;
        });

        if (emptyMsg) {
            var noHit = q !== "" && visibleCount === 0;
            if (noHit) emptyMsg.textContent = "找不到符合「" + query.trim() + "」的球員。";
            emptyMsg.hidden = !noHit;
        }
    }

    // 更新放大鏡圓鈕的「篩選中」指示（右上角小圓點）
    function updateIndicators(query) {
        if (trigger) trigger.classList.toggle("is-filtering", query.trim() !== "");
    }

    // 任一輸入框變動 → 同步另一個 → 重新篩選
    function handleInput(source) {
        var query = source.value;
        inputs.forEach(function (el) {
            if (el !== source) el.value = query;
        });
        filterCards(query);
        updateIndicators(query);
    }

    inputs.forEach(function (el) {
        var onChange = function () { handleInput(el); };
        el.addEventListener("input", onChange);
        // Safari 舊版按原生清除叉叉時不一定送出 input，補聽 search 事件
        el.addEventListener("search", onChange);
    });

    /* ─── 手機版搜尋模式切換 ─── */

    var container = trigger ? trigger.closest(".index-controls, .index-intro") : null;
    // 搜尋模式下會被 CSS 收合成 0 寬的區塊（首頁是排序按鈕、退休頁是說明文字）
    var collapsible = container ? container.querySelector(".sort-group, .index-intro-text") : null;

    /* 放大鏡的位移動畫（FLIP）
     *
     * 為什麼不交給 CSS 過渡：進出搜尋模式時放大鏡的位置是由 order（3 ⇄ 0）與
     * margin-left（auto ⇄ 0）決定的，這兩個都不適合直接過渡 ——
     *   · margin-left: auto 不可插值，會直接瞬移（實測開啟瞬間橫跳 113px）；
     *   · order 反而「可以」插值（規範定義為整數），一旦 transition 寫成
     *     all/var(--ease) 就會被拆成 3 → 2 → 1 → 0 三次離散跳格，
     *     那正是看起來掉幀的來源。
     * 所以 layout 一律讓它瞬間到位，再用 FLIP 量出前後位置差，
     * 以 transform 補回去做動畫 —— 只動 transform，交由合成器執行。
     */
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    // 顏色類過渡的真相來源在 CSS（.search-trigger 的 transition），這裡讀來接在 transform 後面，
    // 免得行內 transition 把亮起的顏色動畫蓋掉
    var colorTransition = trigger ? getComputedStyle(trigger).transition : "";
    var TRIGGER_EASE = "transform .32s cubic-bezier(.22, 1, .36, 1)";

    function withTransform(spec) {
        return colorTransition ? spec + ", " + colorTransition : spec;
    }

    // mutate() 內做真正的 class 切換；前後各量一次位置，差值用 transform 播回來
    function flipTrigger(mutate) {
        if (!trigger || reduceMotion.matches) { mutate(); return; }
        var first = trigger.getBoundingClientRect();
        mutate();
        var last = trigger.getBoundingClientRect();
        var dx = first.left - last.left;
        var dy = first.top - last.top;
        if (!dx && !dy) return;

        trigger.style.transition = withTransform("transform 0s");
        trigger.style.transform = "translate3d(" + dx + "px, " + dy + "px, 0)";
        void trigger.offsetWidth;               // 強制回流，確保起始位置已生效
        requestAnimationFrame(function () {
            trigger.style.transition = withTransform(TRIGGER_EASE);
            trigger.style.transform = "translate3d(0, 0, 0)";
        });
    }

    // 動畫結束就把行內樣式清掉，:active 的 scale 回饋才能拿回 transform
    if (trigger) {
        trigger.addEventListener("transitionend", function (e) {
            if (e.propertyName !== "transform") return;
            trigger.style.transition = "";
            trigger.style.transform = "";
        });
    }

    if (container && trigger && inlineInput && cancelBtn) {
        var openSearch = function () {
            flipTrigger(function () { container.classList.add("search-mode"); });
            trigger.setAttribute("aria-expanded", "true");
            trigger.setAttribute("tabindex", "-1");
            inlineInput.removeAttribute("tabindex");
            cancelBtn.removeAttribute("tabindex");
            // 收合的區塊只是視覺上寬高歸零，仍在 Tab 順序與無障礙樹裡 → 用 inert 一併移除
            if (collapsible) collapsible.inert = true;
            inlineInput.focus();
        };

        var closeSearch = function () {
            flipTrigger(function () { container.classList.remove("search-mode"); });
            trigger.setAttribute("aria-expanded", "false");
            trigger.removeAttribute("tabindex");
            inlineInput.setAttribute("tabindex", "-1");
            cancelBtn.setAttribute("tabindex", "-1");
            if (collapsible) collapsible.inert = false;
            inlineInput.blur();
            if (inlineInput.value !== "") {
                inlineInput.value = "";
                handleInput(inlineInput);
            }
        };

        trigger.addEventListener("click", openSearch);
        cancelBtn.addEventListener("click", closeSearch);

        // 綁在 document 即可涵蓋輸入框內按 Esc（事件會冒泡上來）
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && container.classList.contains("search-mode")) {
                e.preventDefault();
                closeSearch();
            }
        });
    }
});
