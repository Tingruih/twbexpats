/**
 * Reveal macOS overlay scrollbars when the pointer reaches a table's bottom edge.
 * A one-pixel scroll and immediate restore asks the browser to show its native
 * scrollbar without changing the user's horizontal position.
 */
(function () {
    'use strict';

    const BOTTOM_HOT_ZONE = 28;
    const REVEAL_COOLDOWN = 600;
    const lastReveal = new WeakMap();

    function revealScrollbar(scroller) {
        if (scroller.scrollWidth <= scroller.clientWidth + 1) return;

        const now = performance.now();
        if (now - (lastReveal.get(scroller) || 0) < REVEAL_COOLDOWN) return;
        lastReveal.set(scroller, now);

        const originalLeft = scroller.scrollLeft;
        const maxLeft = scroller.scrollWidth - scroller.clientWidth;
        const nudgedLeft = originalLeft < maxLeft ? originalLeft + 1 : originalLeft - 1;

        scroller.scrollLeft = nudgedLeft;
        requestAnimationFrame(function () {
            scroller.scrollLeft = originalLeft;
        });
    }

    document.addEventListener('pointermove', function (event) {
        if (event.pointerType && event.pointerType !== 'mouse') return;

        const scroller = event.target.closest('.table-scroll, .pitch-log-scroll');
        if (!scroller) return;

        const rect = scroller.getBoundingClientRect();
        const distanceFromBottom = rect.bottom - event.clientY;
        if (distanceFromBottom >= 0 && distanceFromBottom <= BOTTOM_HOT_ZONE) {
            revealScrollbar(scroller);
        }
    }, { passive: true });
})();
