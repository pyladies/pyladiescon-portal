/* The export scope form (templates/speakers/media_export.html).
 *
 * Two conveniences, no submit: check or clear a whole group at once
 * (data-select="kinds:all", "sessions:none", "group:<n>:all", "all:all"
 * and so on), and the session picker: it is a fieldset that follows the
 * "every session" / "only these" radios, with a filter field that hides
 * the sessions whose title does not contain what was typed, and a line
 * that counts what is chosen. The count of files still updates on
 * "Apply selection".
 */
(function () {
    "use strict";

    function boxes(form, group) {
        var rows = form.querySelectorAll('.session-picker-list .form-check' + (group ? '[data-group="' + group + '"]' : ""));
        return Array.prototype.map.call(rows, function (row) { return row.querySelector("input[name=sessions]"); });
    }

    function apply(form, parts) {
        var on = parts[parts.length - 1] === "all";
        var group = parts[0];
        if (group === "kinds" || group === "all") {
            form.querySelectorAll("input[type=checkbox][name=kinds]").forEach(function (box) { box.checked = on; });
        }
        if (group === "sessions" || group === "all") {
            boxes(form).forEach(function (box) { box.checked = on; });
        }
        if (group === "group") {
            boxes(form, parts[1]).forEach(function (box) { box.checked = on; });
        }
        if (group === "all") {
            var mode = form.querySelector('input[name=sessions_mode][value="' + (on ? "some" : "all") + '"]');
            if (mode) { mode.checked = true; }
        }
        sync(form);
    }

    function sync(form) {
        var picker = form.querySelector("#session-picker");
        if (!picker) { return; }
        var some = form.querySelector('input[name=sessions_mode][value="some"]');
        picker.disabled = !(some && some.checked);
        var chosen = boxes(form).filter(function (box) { return box.checked; }).length;
        var summary = picker.querySelector("[data-role=session-summary]");
        if (summary) {
            summary.textContent = picker.disabled ? "" : (chosen === 1 ? "1 session chosen" : chosen + " sessions chosen");
        }
    }

    function filter(form, text) {
        var needle = text.trim().toLowerCase();
        form.querySelectorAll(".session-picker-list .form-check").forEach(function (row) {
            row.hidden = needle !== "" && row.dataset.title.indexOf(needle) === -1;
        });
    }

    function main() {
        var form = document.getElementById("export-scope");
        if (!form) { return; }
        form.addEventListener("click", function (event) {
            var button = event.target.closest("[data-select]");
            if (!button) { return; }
            event.preventDefault();
            apply(form, button.dataset.select.split(":"));
        });
        form.addEventListener("change", function (event) {
            if (event.target.name === "sessions_mode" || event.target.name === "sessions") { sync(form); }
        });
        var search = form.querySelector("[data-role=session-filter]");
        if (search) {
            search.addEventListener("input", function () { filter(form, search.value); });
        }
        sync(form);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", main);
    } else {
        main();
    }
})();
