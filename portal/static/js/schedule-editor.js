/* The schedule editor (speakers, task 4.2).
 *
 * Every mutation goes through the one slot endpoint each card carries in
 * data-slot-url: drops and the keyboard form PATCH, "Remove" DELETEs. On
 * success the board partial (grid plus sidebar) is refetched whole, so the
 * warnings are always what is shown. Times are UTC end to end; the
 * timezone switcher only relabels the [data-utc] elements.
 */
(function () {
    "use strict";

    var STEP_MINUTES = 15;
    var dragged = null;
    var resizing = null;

    function board() {
        return document.getElementById("schedule-board");
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
        var url = board().dataset.boardUrl;
        var grid = board().querySelector(".schedule-scroll");
        var list = board().querySelector(".schedule-unscheduled");
        var kept = {
            top: grid ? grid.scrollTop : 0,
            left: grid ? grid.scrollLeft : 0,
            list: list ? list.scrollTop : 0
        };
        return fetch(url)
            .then(function (response) { return response.text(); })
            .then(function (html) {
                board().innerHTML = html;
                var freshGrid = board().querySelector(".schedule-scroll");
                if (freshGrid) {
                    freshGrid.scrollTop = kept.top;
                    freshGrid.scrollLeft = kept.left;
                }
                var freshList = board().querySelector(".schedule-unscheduled");
                if (freshList) freshList.scrollTop = kept.list;
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
    /* The dashed footprint showing where a drop would land. */
    function dropPreview() {
        var grid = board().querySelector(".schedule-grid");
        var ghost = grid.querySelector(".schedule-drop-preview");
        if (!ghost) {
            ghost = document.createElement("div");
            ghost.className = "schedule-drop-preview";
            var label = document.createElement("span");
            label.className = "schedule-drop-label";
            ghost.appendChild(label);
            grid.appendChild(ghost);
        }
        return ghost;
    }

    function hideDropPreview() {
        var grid = board().querySelector(".schedule-grid");
        var ghost = grid && grid.querySelector(".schedule-drop-preview");
        if (ghost) {
            ghost.style.display = "none";
            ghost.classList.remove("schedule-drop-band");
            ghost.querySelector(".schedule-drop-label").textContent = "";
        }
    }

    document.addEventListener("dragstart", function (event) {
        var card = event.target.closest("[data-slot-url]");
        if (!card) return;
        dragged = {
            url: card.dataset.slotUrl,
            minutes: parseInt(card.dataset.minutes, 10) || 30
        };
        event.dataTransfer.effectAllowed = "move";
        /* The drag image is painted from an off-screen clone: snapshots
         * of the live element pulled overlapping neighbours (and once,
         * a stray text selection) into the picture. */
        var rect = card.getBoundingClientRect();
        var image = card.cloneNode(true);
        image.classList.add("schedule-drag-image");
        image.style.width = Math.round(rect.width) + "px";
        document.body.appendChild(image);
        event.dataTransfer.setDragImage(
            image,
            event.clientX - rect.left,
            event.clientY - rect.top
        );
        setTimeout(function () { image.remove(); }, 0);
    });
    document.addEventListener("dragover", function (event) {
        if (!dragged) return;
        var cell = event.target.closest(".schedule-cell");
        if (!cell) {
            if (!event.target.closest(".schedule-grid")) hideDropPreview();
            return;
        }
        event.preventDefault();
        cell.classList.add("schedule-drop");
        var ghost = dropPreview();
        var span = Math.max(1, Math.round(dragged.minutes / STEP_MINUTES));
        ghost.style.gridRow = cell.style.gridRow + " / span " + span;
        ghost.style.gridColumn = cell.dataset.room
            ? cell.style.gridColumn
            : "2 / -1";
        ghost.style.display = "flex";
    });
    document.addEventListener("dragleave", function (event) {
        var cell = event.target.closest(".schedule-cell");
        if (cell) cell.classList.remove("schedule-drop");
    });
    document.addEventListener("drop", function (event) {
        var cell = event.target.closest(".schedule-cell");
        if (!dragged || !cell) return;
        event.preventDefault();
        hideDropPreview();
        send(dragged.url, "PATCH", {
            room: cell.dataset.room || null,
            start: cell.dataset.time
        });
        dragged = null;
    });

    document.addEventListener("dragend", function () {
        hideDropPreview();
        dragged = null;
    });

    /* Resizing: the handle at a card's bottom edge, in 15-minute steps. */
    document.addEventListener("pointerdown", function (event) {
        var handle = event.target.closest(".schedule-resize");
        if (!handle) return;
        var card = handle.closest(".schedule-card");
        var cell = board().querySelector(".schedule-cell");
        resizing = {
            url: card.dataset.slotUrl,
            minutes: parseInt(card.dataset.minutes, 10),
            rowHeight: cell ? cell.offsetHeight : 18,
            startY: event.clientY,
            row: parseInt(card.style.gridRow, 10),
            column: card.style.gridColumn,
            band: card.classList.contains("schedule-band")
        };
        event.preventDefault();
    });

    function resizeMinutes(event) {
        var rows = Math.round(
            (event.clientY - resizing.startY) / resizing.rowHeight
        );
        return Math.max(STEP_MINUTES, resizing.minutes + rows * STEP_MINUTES);
    }
    document.addEventListener("pointermove", function (event) {
        if (!resizing) return;
        event.preventDefault();
        var minutes = resizeMinutes(event);
        var ghost = dropPreview();
        ghost.style.gridRow =
            resizing.row + " / span " +
            Math.max(1, Math.round(minutes / STEP_MINUTES));
        ghost.style.gridColumn = resizing.column;
        ghost.classList.toggle("schedule-drop-band", resizing.band);
        ghost.querySelector(".schedule-drop-label").textContent =
            minutes + " min";
        ghost.style.display = "flex";
    });
    document.addEventListener("pointerup", function (event) {
        if (!resizing) return;
        hideDropPreview();
        var minutes = resizeMinutes(event);
        if (minutes !== resizing.minutes) {
            send(resizing.url, "PATCH", { duration: minutes });
        }
        resizing = null;
    });
    document.addEventListener("pointercancel", function () {
        if (!resizing) return;
        hideDropPreview();
        resizing = null;
    });

    /* Open card popovers close on Cancel, Escape, or a click elsewhere. */
    function closeCardMenus(except) {
        document.querySelectorAll(
            "details.schedule-card-menu[open]"
        ).forEach(function (menu) {
            if (menu !== except) menu.removeAttribute("open");
        });
    }

    document.addEventListener("click", function (event) {
        closeCardMenus(event.target.closest("details.schedule-card-menu"));
    });

    /* A card clips its own content (long titles), which would clip an
     * open popover to the card's height too; while a menu is open the
     * card lifts the clipping and stacks above its neighbours. The
     * toggle event does not bubble, so it is captured. */
    document.addEventListener(
        "toggle",
        function (event) {
            var menu = event.target;
            if (!menu.classList ||
                    !menu.classList.contains("schedule-card-menu")) {
                return;
            }
            var card = menu.closest(".schedule-card, .schedule-pending");
            if (card) {
                card.classList.toggle("schedule-card-open", menu.open);
            }
        },
        true
    );

    /* The keyboard form: Place applies every field, Remove unschedules,
     * Cancel folds the popover away. */
    document.addEventListener("click", function (event) {
        var button = event.target.closest("[data-action]");
        if (!button) return;
        var form = button.closest("[data-slot-form]");
        if (!form) return;
        if (button.dataset.action === "slot-cancel") {
            var menu = button.closest("details.schedule-card-menu");
            if (menu) menu.removeAttribute("open");
            return;
        }
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

    /* Click an empty cell to add something right there. */
    var panelCell = null;

    function cellPanel() {
        return document.getElementById("schedule-cell-panel");
    }

    function hideCellPanel() {
        var panel = cellPanel();
        if (panel) panel.classList.add("d-none");
        panelCell = null;
    }

    function timeLabel(iso) {
        var select = document.getElementById("schedule-timezone");
        var zone = select && select.value !== "local" ? select.value : undefined;
        try {
            return new Intl.DateTimeFormat(undefined, {
                weekday: "short",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
                timeZone: zone
            }).format(new Date(iso));
        } catch (error) {
            return iso;
        }
    }

    document.addEventListener("click", function (event) {
        if (event.target.closest("[data-action=cell-panel-close]")) {
            hideCellPanel();
            return;
        }
        var option = event.target.closest(".schedule-place-option");
        if (option && panelCell) {
            send(option.dataset.slotUrl, "PATCH", {
                room: panelCell.dataset.room || null,
                start: panelCell.dataset.time
            });
            hideCellPanel();
        }
    });

    document.addEventListener("click", function (event) {
        var panel = cellPanel();
        if (!panel) return;
        if (event.target.closest("#schedule-cell-panel")) return;
        var cell = event.target.closest(".schedule-cell");
        if (!cell || event.target.closest(".schedule-card")) {
            hideCellPanel();
            return;
        }
        panelCell = cell;
        panel.querySelector("[data-role=cell-start]").value =
            cell.dataset.time;
        panel.querySelector("[data-role=cell-room]").value =
            cell.dataset.room || "";
        panel.querySelector("[data-role=cell-label]").textContent =
            timeLabel(cell.dataset.time) + " \u00b7 " + cell.dataset.roomName;
        panel.classList.remove("d-none");
        panel.style.left =
            Math.min(event.clientX, window.innerWidth - 300) + "px";
        panel.style.top =
            Math.min(event.clientY, window.innerHeight - 340) + "px";
    });

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        hideCellPanel();
        closeCardMenus();
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
