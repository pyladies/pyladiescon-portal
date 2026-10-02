/* Deleting a file line, every version of it (templates/speakers/
 * _media_delete_modal.html). One dialog per page; the Delete button that
 * opened it says which line in data attributes, and the submit button
 * stays disabled until the typed name matches the one shown. The server
 * checks the name again.
 */
(function () {
    "use strict";

    var modal = document.getElementById("media-delete-modal");
    if (!modal) { return; }
    var form = modal.querySelector("[data-role=form]");
    var name = modal.querySelector("[data-role=name]");
    var label = modal.querySelector("[data-role=label]");
    var versions = modal.querySelector("[data-role=versions]");
    var submit = modal.querySelector("[data-role=submit]");
    var input = modal.querySelector("#media-delete-confirm");

    function check() {
        submit.disabled = input.value.trim() !== name.textContent;
    }

    modal.addEventListener("show.bs.modal", function (event) {
        var source = event.relatedTarget;
        if (!source) { return; }
        form.action = source.dataset.action;
        name.textContent = source.dataset.name;
        label.textContent = source.dataset.label;
        versions.textContent = source.dataset.versions;
        input.value = "";
        check();
    });
    modal.addEventListener("shown.bs.modal", function () { input.focus(); });
    input.addEventListener("input", check);
    form.addEventListener("submit", function (event) {
        if (submit.disabled) { event.preventDefault(); }
    });
})();
