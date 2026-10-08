/* A "Copy" button next to a read-only field: data-copy-target names the
 * field's id. Falls back to selecting the text where the clipboard API is
 * unavailable (plain http, older browsers). */
(function () {
    "use strict";
    document.addEventListener("click", function (event) {
        var button = event.target.closest("[data-copy-target]");
        if (!button) return;
        var field = document.getElementById(button.dataset.copyTarget);
        if (!field) return;
        field.select();
        var done = function () {
            var label = button.textContent;
            button.textContent = button.dataset.copiedLabel || "Copied";
            window.setTimeout(function () { button.textContent = label; }, 1500);
        };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(field.value).then(done, function () {});
        } else {
            /* Plain http or an old browser: the text is selected, so say so. */
            var label = button.textContent;
            button.textContent = "Selected, press Ctrl+C";
            window.setTimeout(function () { button.textContent = label; }, 2500);
        }
    });
})();
