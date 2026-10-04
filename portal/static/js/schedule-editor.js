/* The schedule editor (speakers, task 4.2).
 *
 * Every mutation goes through the one slot endpoint each card carries in
 * data-slot-url: drops and the keyboard form PATCH, "Remove" DELETEs. On
 * success the grid partial is refetched whole, so the server's layout and
 * warnings are always what is shown. Times are UTC end to end; the
 * timezone switcher only relabels the [data-utc] elements.
 */
(function () {
    "use strict";

    var STEP_MINUTES = 15;
    var dragged = null;
    var resizing = null;

    function grid() {
        return document.getElementById("schedule-grid");
    }

    function csrfToken() {
        var input = document.querySelector("[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    function showBox(id, messages) {
        var box = document.getElementById(id);
        if (!box) return;
        if (!messages || !messages.length) {
            box.classList.add("d-none");
            box.textContent = "";
            return;
        }
        box.textContent = messages.join(" ");
        box.classList.remove("d-none");
    }

    function refresh() {
        var url = grid().dataset.gridUrl;
        return fetch(url)
            .then(function (response) { return response.text(); })
            .then(function (html) {
                grid().innerHTML = html;
                applyTimezone();
            });
    }

    function send(url, method, body) {
        return fetch(url, {
            method: method,
            headers: {
                "X-CSRFToken": csrfToken(),
                "Content-Type": "application/json"
            },
            body: body === undefined ? undefined : JSON.stringify(body)
        }).then(function (response) {
            return response.json().catch(function () { return {}; }).then(
                function (data) {
                    if (!response.ok) {
                        showBox("schedule-alert", data.errors || [
                            "The change was refused."
                        ]);
                        return null;
                    }
                    showBox("schedule-alert", []);
                    showBox("schedule-warnings", data.warnings || []);
                    return refresh().then(function () { return data; });
                }
            );
        });
    }

    /* Dragging: whole cards onto cells. */
    document.addEventListener("dragstart", function (event) {
        var card = event.target.closest("[data-slot-url]");
        if (!card) return;
        dragged = card.dataset.slotUrl;
        event.dataTransfer.effectAllowed = "move";
    });
    document.addEventListener("dragover", function (event) {
        var cell = event.target.closest(".schedule-cell");
        if (!dragged || !cell) return;
        event.preventDefault();
        cell.classList.add("schedule-drop");
    });
    document.addEventListener("dragleave", function (event) {
        var cell = event.target.closest(".schedule-cell");
        if (cell) cell.classList.remove("schedule-drop");
    });
    document.addEventListener("drop", function (event) {
        var cell = event.target.closest(".schedule-cell");
        if (!dragged || !cell) return;
        event.preventDefault();
        send(dragged, "PATCH", {
            room: cell.dataset.room || null,
            start: cell.dataset.time
        });
        dragged = null;
    });

    /* Resizing: the handle at a card's bottom edge, in 15-minute steps. */
    document.addEventListener("pointerdown", function (event) {
        var handle = event.target.closest(".schedule-resize");
        if (!handle) return;
        var card = handle.closest(".schedule-card");
        var cell = grid().querySelector(".schedule-cell");
        resizing = {
            url: card.dataset.slotUrl,
            minutes: parseInt(card.dataset.minutes, 10),
            rowHeight: cell ? cell.offsetHeight : 18,
            startY: event.clientY
        };
        event.preventDefault();
    });
    document.addEventListener("pointermove", function (event) {
        if (!resizing) return;
        event.preventDefault();
    });
    document.addEventListener("pointerup", function (event) {
        if (!resizing) return;
        var rows = Math.round(
            (event.clientY - resizing.startY) / resizing.rowHeight
        );
        var minutes = Math.max(
            STEP_MINUTES, resizing.minutes + rows * STEP_MINUTES
        );
        if (minutes !== resizing.minutes) {
            send(resizing.url, "PATCH", { duration: minutes });
        }
        resizing = null;
    });

    /* The keyboard form: Place applies every field, Remove unschedules. */
    document.addEventListener("click", function (event) {
        var button = event.target.closest("[data-action]");
        if (!button) return;
        var form = button.closest("[data-slot-form]");
        if (!form) return;
        if (button.dataset.action === "slot-remove") {
            send(form.dataset.url, "DELETE");
            return;
        }
        if (button.dataset.action !== "slot-apply") return;
        var value = function (name) {
            return form.querySelector("[data-field=" + name + "]").value;
        };
        var time = value("time");
        if (!time) {
            showBox("schedule-alert", ["Give the slot a start time."]);
            return;
        }
        send(form.dataset.url, "PATCH", {
            room: value("room") || null,
            start: value("date") + "T" + time + ":00+00:00",
            duration: parseInt(value("duration"), 10) || STEP_MINUTES
        });
    });

    /* The timezone switcher relabels every [data-utc] element. */
    function applyTimezone() {
        var select = document.getElementById("schedule-timezone");
        if (!select) return;
        var zone = select.value === "local" ? undefined : select.value;
        var formatter;
        try {
            formatter = new Intl.DateTimeFormat(undefined, {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
                timeZone: zone
            });
        } catch (error) {
            return;
        }
        document.querySelectorAll("[data-utc]").forEach(function (element) {
            element.textContent = formatter.format(
                new Date(element.dataset.utc)
            );
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var select = document.getElementById("schedule-timezone");
        if (!select) return;
        var remembered = null;
        try {
            remembered = window.localStorage.getItem("schedule-timezone");
        } catch (error) {
            remembered = null;
        }
        if (remembered) {
            var known = Array.prototype.some.call(
                select.options,
                function (option) { return option.value === remembered; }
            );
            if (known) select.value = remembered;
        }
        select.addEventListener("change", function () {
            try {
                window.localStorage.setItem("schedule-timezone", select.value);
            } catch (error) {
                /* Private windows forget the choice; the page still works. */
            }
            applyTimezone();
        });
        applyTimezone();
    });
})();
