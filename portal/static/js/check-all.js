/* "Select all" / "Deselect all" for a list of checkboxes: a button with
 * data-check-all="<input name>" and data-checked="true" or "false" sets
 * every enabled box of that name in the same form. Disabled boxes keep
 * their state; nothing is saved until the form is submitted. */
(function () {
    "use strict";
    document.addEventListener("click", function (event) {
        var button = event.target.closest("[data-check-all]");
        if (!button || !button.form) return;
        var checked = button.dataset.checked === "true";
        button.form
            .querySelectorAll('input[type="checkbox"][name="' + button.dataset.checkAll + '"]')
            .forEach(function (box) {
                if (!box.disabled) box.checked = checked;
            });
    });
})();
