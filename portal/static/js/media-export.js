/* Bulk download to a folder (speakers, design §8.8, "Bulk download").
 *
 * The export page lists the files with presigned links (entries.json).
 * On a browser with the File System Access API the person picks a folder
 * and each file streams straight from the bucket into it, laid out by
 * session and kind, with the manifest written first. A file already
 * there with the right size is skipped, so running it again only fetches
 * what is missing; each transfer is retried a few times.
 *
 * Markup: #folder-download with data-entries-url, [data-role=start],
 * [data-role=progress] (a .progress-bar whose parent is hidden until
 * running), [data-role=status].
 */
(function () {
    "use strict";

    var RETRIES = 3;

    function fmtBytes(n) {
        if (n < 1024) { return n + " B"; }
        var units = ["KB", "MB", "GB", "TB"];
        var i = -1;
        do { n = n / 1024; i += 1; } while (n >= 1024 && i < units.length - 1);
        return n.toFixed(n < 10 ? 1 : 0) + " " + units[i];
    }

    function sleep(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    async function dirFor(root, path) {
        var parts = path.split("/");
        var dir = root;
        for (var i = 0; i < parts.length - 1; i += 1) {
            dir = await dir.getDirectoryHandle(parts[i], {create: true});
        }
        return {dir: dir, name: parts[parts.length - 1]};
    }

    async function existingSize(root, path) {
        try {
            var where = await dirFor(root, path);
            var handle = await where.dir.getFileHandle(where.name);
            var file = await handle.getFile();
            return file.size;
        } catch (e) {
            return -1;
        }
    }

    async function writeText(root, path, text) {
        var where = await dirFor(root, path);
        var handle = await where.dir.getFileHandle(where.name, {create: true});
        var writable = await handle.createWritable();
        await writable.write(text);
        await writable.close();
    }

    async function fetchInto(root, entry, onProgress) {
        var where = await dirFor(root, entry.path);
        var handle = await where.dir.getFileHandle(where.name, {create: true});
        var writable = await handle.createWritable();
        try {
            var response = await fetch(entry.url);
            if (!response.ok) { throw new Error("the bucket answered " + response.status); }
            var reader = response.body.getReader();
            var got = 0;
            for (;;) {
                var step = await reader.read();
                if (step.done) { break; }
                await writable.write(step.value);
                got += step.value.length;
                onProgress(got);
            }
            await writable.close();
        } catch (error) {
            try { await writable.abort(); } catch (e) { /* nothing to undo */ }
            throw error;
        }
    }

    function main() {
        var root = document.getElementById("folder-download");
        if (!root) { return; }
        var start = root.querySelector("[data-role=start]");
        var bar = root.querySelector("[data-role=progress]");
        var status = root.querySelector("[data-role=status]");
        if (!window.showDirectoryPicker) {
            return;  // the page already says to use the script
        }
        start.disabled = false;
        status.textContent = "";

        start.addEventListener("click", async function () {
            var folder;
            try {
                folder = await window.showDirectoryPicker({mode: "readwrite"});
            } catch (e) {
                return;  // cancelled
            }
            start.disabled = true;
            bar.parentElement.hidden = false;
            status.className = "mt-2 text-secondary";
            status.textContent = "Reading the export…";
            var data;
            try {
                var response = await fetch(root.dataset.entriesUrl, {credentials: "same-origin"});
                if (!response.ok) { throw new Error("the portal answered " + response.status); }
                data = await response.json();
            } catch (error) {
                status.className = "mt-2 text-danger";
                status.textContent = "Could not read the export: " + error.message;
                start.disabled = false;
                return;
            }
            var total = data.files.reduce(function (sum, f) { return sum + f.size; }, 0);
            var done = 0;
            var skipped = 0;
            var failed = [];
            await writeText(folder, data.manifest_path, data.manifest);
            for (var i = 0; i < data.files.length; i += 1) {
                var entry = data.files[i];
                var have = await existingSize(folder, entry.path);
                if (have === entry.size) {
                    skipped += 1;
                    done += entry.size;
                    continue;
                }
                var ok = false;
                for (var attempt = 0; attempt < RETRIES && !ok; attempt += 1) {
                    try {
                        await fetchInto(folder, entry, function (got) {
                            var pct = total ? Math.floor((done + got) * 100 / total) : 100;
                            bar.style.width = pct + "%";
                            bar.textContent = pct + "%";
                            status.textContent = (i + 1) + " of " + data.files.length + ": " + entry.path +
                                " · " + fmtBytes(done + got) + " of " + fmtBytes(total);
                        });
                        ok = true;
                    } catch (error) {
                        if (attempt + 1 < RETRIES) { await sleep(1000 * Math.pow(2, attempt)); }
                        else { failed.push(entry.path + " (" + error.message + ")"); }
                    }
                }
                done += entry.size;
            }
            bar.style.width = "100%";
            bar.textContent = "100%";
            if (failed.length) {
                status.className = "mt-2 text-danger";
                status.textContent = "Done with " + failed.length + " failure(s); run again to retry: " + failed.join(", ");
            } else {
                status.className = "mt-2 text-success";
                status.textContent = "Done: " + data.files.length + " files" +
                    (skipped ? " (" + skipped + " already there)" : "") + ", " + fmtBytes(total) + ".";
            }
            start.disabled = false;
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", main);
    } else {
        main();
    }
})();

/* The scope form on the export page (templates/speakers/media_export.html):
 * check or clear a whole group at once. data-select="<group>:<all|none>"
 * with group "kinds" (the checkboxes), "sessions" (the multi-select) or
 * "all" (both). The count still updates on "Apply selection". */
(function () {
    "use strict";

    function apply(form, group, on) {
        if (group === "kinds" || group === "all") {
            form.querySelectorAll('input[type=checkbox][name=kinds]').forEach(function (box) {
                box.checked = on;
            });
        }
        if (group === "sessions" || group === "all") {
            form.querySelectorAll('select[name=sessions] option').forEach(function (option) {
                option.selected = on;
            });
        }
    }

    function main() {
        var form = document.getElementById("export-scope");
        if (!form) { return; }
        form.addEventListener("click", function (event) {
            var button = event.target.closest("[data-select]");
            if (!button) { return; }
            event.preventDefault();
            var parts = button.dataset.select.split(":");
            apply(form, parts[0], parts[1] === "all");
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", main);
    } else {
        main();
    }
})();
