/* On the iframe embed page (speakers/embed.html), inside a frame: tells
 * the host page how tall the program is, so a host that listens can size
 * its iframe to fit, and opens an overlay near the click rather than in
 * the middle of a frame that may be thousands of pixels tall. */
(function () {
    "use strict";
    if (window.parent === window) return;
    var sent = 0;
    function send() {
        var height = Math.ceil(document.documentElement.scrollHeight);
        if (height === sent) return;
        sent = height;
        window.parent.postMessage({ type: "pyladiescon-embed", height: height }, "*");
    }
    new ResizeObserver(send).observe(document.body);
    window.addEventListener("load", send);

    var clickY = 0;
    document.addEventListener("pointerdown", function (event) {
        clickY = event.pageY;
    }, true);
    new MutationObserver(function (records) {
        records.forEach(function (record) {
            var dialog = record.target;
            if (dialog.tagName !== "DIALOG" || !dialog.open) return;
            dialog.style.position = "absolute";
            dialog.style.top = Math.max(8, clickY - 120) + "px";
            dialog.style.marginTop = "0";
        });
    }).observe(document.body, { attributes: true, attributeFilter: ["open"], subtree: true });
})();
