/**
 * avatar-fallback.js — 球員頭像載入失敗備援
 * 載入於：base.j2（每個頁面都有）
 *
 * 分批 lazy 載入交由原生 loading="lazy"（見 index.j2/retired.j2）處理。
 *
 * 作用：所有 .avatar-img 圖片，若載入失敗：
 *  1. 先嘗試 data-cdn-src 屬性指定的 CDN 備用網址
 *  2. 若 CDN 也失敗，隱藏 img 並顯示 .avatar-fallback（文字縮寫頭像）
 */
document.addEventListener("DOMContentLoaded", function () {
    var avatars = document.querySelectorAll(".avatar-img");

    avatars.forEach(function (img) {
        img.addEventListener("error", function () {
            // 第一次失敗：嘗試 CDN 備用來源
            if (!this.dataset.cdnTried) {
                this.dataset.cdnTried = "1";
                var cdn = this.dataset.cdnSrc;
                if (cdn) { this.src = cdn; return; }
            }
            // CDN 也失敗：隱藏圖片，顯示文字縮寫頭像
            this.style.display = "none";
            var fallback = this.parentElement.querySelector(".avatar-fallback");
            if (fallback) fallback.style.display = "flex";
        });
    });
});
