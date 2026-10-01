/* The organizer's session page is split into tabs (templates/speakers/
 * session_detail.html). Links into the page (#checklist, #files, #add-file,
 * #presenters, #details, ...) predate the tabs and are used by redirects,
 * the strip's tiles and the quick actions, so a hash that points inside a
 * hidden tab pane opens that pane first, then scrolls. Choosing a tab
 * writes its anchor into the URL, so a reload comes back to the same tab.
 */
(function () {
    "use strict";

    function paneTrigger(pane) {
        return document.querySelector('[data-bs-target="#' + pane.id + '"]');
    }

    function showFor(hash) {
        if (!hash || hash.length < 2) { return; }
        var target;
        try { target = document.querySelector(hash); } catch (e) { return; }
        if (!target) { return; }
        var pane = target.closest(".tab-pane");
        if (pane && window.bootstrap) {
            var trigger = paneTrigger(pane);
            if (trigger && !trigger.classList.contains("active")) {
                window.bootstrap.Tab.getOrCreateInstance(trigger).show();
            }
        }
        window.setTimeout(function () {
            target.scrollIntoView({block: "start", behavior: "smooth"});
        }, 60);
    }

    document.addEventListener("DOMContentLoaded", function () {
        var tabs = document.getElementById("session-tabs");
        if (!tabs) { return; }
        tabs.addEventListener("shown.bs.tab", function (event) {
            var anchor = event.target.dataset.anchor;
            if (anchor && window.history.replaceState) {
                window.history.replaceState(null, "", "#" + anchor);
            }
        });
        // A pane's own anchor (#checklist, #files, #details, #overview) or
        // anything inside one.
        showFor(window.location.hash);
    });
    window.addEventListener("hashchange", function () {
        showFor(window.location.hash);
    });
})();
