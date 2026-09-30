/* Chunked uploads straight to object storage (speakers, design §8.8).
 *
 * One panel per [data-upload-panel]. The portal opens a multipart upload
 * and hands out presigned part URLs in batches; this file slices the
 * file, PUTs each part to the bucket (a few at a time, with retries),
 * and asks the portal to complete. An unfinished upload is remembered in
 * localStorage under the session and kind, so coming back after a dropped
 * connection or a closed tab picks up where it stopped once the same file
 * is chosen again: the parts the bucket already holds are skipped.
 *
 * Markup contract (templates/speakers/_upload_panel.html):
 *   data-upload-panel            the root
 *   data-start-url               POST to open an upload
 *   data-upload-url              detail URL with "/0/" where the id goes
 *   data-csrf                    the CSRF token
 *   data-storage-key             localStorage key prefix (session + user)
 *   [data-role=file]             <input type=file>
 *   [data-role=kind]             optional <select> (organizer panel)
 *   [data-role=language]         optional <input> (organizer panel)
 *   [data-role=variant]          optional <input> (organizer panel): which of
 *                                several files of one kind (square, gif...)
 *   [data-role=title]            optional <input>: what the file is about;
 *                                prefilled from #upload-titles-<panel> (a JSON
 *                                map "KIND|language" -> title) until typed in
 *   [data-role=start]            the upload button
 *   [data-role=cancel]           cancel/abort
 *   [data-role=progress]         .progress-bar
 *   [data-role=status]           text line
 *   [data-role=resume]           the "unfinished upload" note
 */
(function () {
    "use strict";

    var CONCURRENCY = 3;
    var RETRIES = 5;

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

    function Panel(root) {
        this.root = root;
        this.startUrl = root.dataset.startUrl;
        this.uploadUrl = root.dataset.uploadUrl;
        this.csrf = root.dataset.csrf;
        this.storagePrefix = root.dataset.storageKey;
        this.file = root.querySelector("[data-role=file]");
        this.kind = root.querySelector("[data-role=kind]");
        this.language = root.querySelector("[data-role=language]");
        this.variant = root.querySelector("[data-role=variant]");
        this.title = root.querySelector("[data-role=title]");
        this.lineTitles = {};
        var titlesNode = this.title && root.querySelector('script[id^="upload-titles-"]');
        if (titlesNode) {
            try { this.lineTitles = JSON.parse(titlesNode.textContent) || {}; } catch (e) { this.lineTitles = {}; }
        }
        this.titleTyped = false;
        this.startButton = root.querySelector("[data-role=start]");
        this.cancelButton = root.querySelector("[data-role=cancel]");
        this.bar = root.querySelector("[data-role=progress]");
        this.status = root.querySelector("[data-role=status]");
        this.resumeNote = root.querySelector("[data-role=resume]");
        this.cancelled = false;
        this.running = false;

        var self = this;
        this.startButton.addEventListener("click", function () { self.begin(); });
        this.cancelButton.addEventListener("click", function () { self.cancel(); });
        if (this.kind) {
            this.kind.addEventListener("change", function () { self.showResume(); self.prefillTitle(); });
        }
        if (this.language) {
            this.language.addEventListener("input", function () { self.prefillTitle(); });
        }
        if (this.title) {
            this.title.addEventListener("input", function () { self.titleTyped = self.title.value.trim() !== ""; });
        }
        this.showResume();
        this.prefillTitle();
    }

    Panel.prototype.currentKind = function () {
        return this.kind ? this.kind.value : this.root.dataset.kind;
    };

    Panel.prototype.currentLanguage = function () {
        return this.language ? this.language.value.trim() : "";
    };

    Panel.prototype.currentVariant = function () {
        return this.variant ? this.variant.value.trim() : "";
    };

    Panel.prototype.currentTitle = function () {
        return this.title ? this.title.value.trim() : "";
    };

    /* The line (kind and language) may already have a title: offer it,
     * and stop offering once the person has typed their own. */
    Panel.prototype.prefillTitle = function () {
        if (!this.title || this.titleTyped) { return; }
        var known = this.lineTitles[this.currentKind() + "|" + this.currentLanguage()] || "";
        this.title.value = known;
    };

    Panel.prototype.storageKey = function () {
        return this.storagePrefix + ":" + this.currentKind() + ":" + this.currentVariant();
    };

    Panel.prototype.remembered = function () {
        try {
            var raw = localStorage.getItem(this.storageKey());
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    };

    Panel.prototype.remember = function (upload, file) {
        try {
            localStorage.setItem(this.storageKey(), JSON.stringify({
                upload: upload.upload,
                filename: file.name,
                size: file.size,
                expires_at: upload.expires_at
            }));
        } catch (e) { /* private mode: resume is a convenience */ }
    };

    Panel.prototype.forget = function () {
        try { localStorage.removeItem(this.storageKey()); } catch (e) { /* ignore */ }
    };

    Panel.prototype.showResume = function () {
        var saved = this.remembered();
        if (saved && new Date(saved.expires_at) < new Date()) {
            this.forget();
            saved = null;
        }
        if (!this.resumeNote) { return; }
        if (saved) {
            this.resumeNote.hidden = false;
            this.resumeNote.querySelector("[data-role=resume-name]").textContent =
                saved.filename + " (" + fmtBytes(saved.size) + ")";
        } else {
            this.resumeNote.hidden = true;
        }
    };

    Panel.prototype.say = function (text, tone) {
        this.status.textContent = text;
        this.status.className = "small mt-2 " + (tone || "text-secondary");
    };

    Panel.prototype.progress = function (done, total) {
        var pct = total ? Math.floor(done * 100 / total) : 0;
        this.bar.style.width = pct + "%";
        this.bar.setAttribute("aria-valuenow", pct);
        this.bar.textContent = pct + "%";
    };

    Panel.prototype.busy = function (on) {
        this.running = on;
        this.startButton.disabled = on;
        this.file.disabled = on;
        if (this.kind) { this.kind.disabled = on; }
        if (this.language) { this.language.disabled = on; }
        if (this.variant) { this.variant.disabled = on; }
        if (this.title) { this.title.disabled = on; }
        this.cancelButton.hidden = !on;
        this.bar.parentElement.hidden = !on;
    };

    Panel.prototype.api = function (method, url, body) {
        var options = {
            method: method,
            credentials: "same-origin",
            headers: {"X-CSRFToken": this.csrf, "Accept": "application/json"}
        };
        if (body !== undefined) {
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(body);
        }
        return fetch(url, options).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (data) {
                if (!response.ok) {
                    throw new Error(data.error || ("The portal answered " + response.status + "."));
                }
                return data;
            });
        });
    };

    Panel.prototype.urlFor = function (uploadId, suffix) {
        return this.uploadUrl.replace("/0/", "/" + uploadId + "/") + (suffix || "");
    };

    Panel.prototype.begin = function () {
        var file = this.file.files[0];
        if (!file) {
            this.say("Choose a file first.", "text-danger");
            return;
        }
        if (!this.currentKind()) {
            this.say("Choose what kind of file this is.", "text-danger");
            return;
        }
        var self = this;
        var saved = this.remembered();
        this.cancelled = false;
        this.busy(true);
        this.progress(0, file.size);

        var opening;
        if (saved && saved.filename === file.name && saved.size === file.size) {
            this.say("Picking up the unfinished upload of " + file.name + "…");
            opening = this.api("GET", this.urlFor(saved.upload)).then(function (upload) {
                if (upload.status !== "STARTED") {
                    throw new Error("stale");
                }
                return upload;
            }).catch(function () {
                self.forget();
                return self.open(file);
            });
        } else {
            if (saved) {
                // A different file: the old upload is given up.
                this.api("POST", this.urlFor(saved.upload, "abort/")).catch(function () {});
                this.forget();
            }
            opening = this.open(file);
        }

        opening.then(function (upload) {
            self.remember(upload, file);
            return self.send(upload, file);
        }).then(function (result) {
            self.forget();
            self.progress(file.size, file.size);
            self.say("Uploaded: version " + result.asset.version + ". Reloading…", "text-success");
            window.location.reload();
        }).catch(function (error) {
            self.busy(false);
            if (self.cancelled) {
                self.say("Upload cancelled.", "text-secondary");
            } else {
                self.say("Upload stopped: " + error.message + " Choose the same file and try again to continue.", "text-danger");
            }
            self.showResume();
        });
    };

    Panel.prototype.open = function (file) {
        this.say("Opening the upload…");
        return this.api("POST", this.startUrl, {
            kind: this.currentKind(),
            language: this.currentLanguage(),
            variant: this.currentVariant(),
            title: this.currentTitle(),
            filename: file.name,
            size_bytes: file.size,
            content_type: file.type || "application/octet-stream"
        });
    };

    Panel.prototype.send = function (upload, file) {
        var self = this;
        var partSize = upload.part_size;
        var total = upload.parts_total;
        var etags = {};
        var doneBytes = 0;
        var inFlight = {};
        var urls = {};
        var next = 1;

        (upload.received || []).forEach(function (part) {
            etags[part.number] = part.etag;
            doneBytes += part.size;
        });
        (upload.parts || []).forEach(function (part) { urls[part.number] = part.url; });

        function report() {
            var flying = 0;
            Object.keys(inFlight).forEach(function (k) { flying += inFlight[k]; });
            self.progress(doneBytes + flying, file.size);
            self.say(fmtBytes(doneBytes + flying) + " of " + fmtBytes(file.size) +
                " · part " + Math.min(next, total) + " of " + total);
        }

        function urlFor(number) {
            if (urls[number]) { return Promise.resolve(urls[number]); }
            return self.api("GET", self.urlFor(upload.upload, "parts/?from=" + number)).then(function (data) {
                data.parts.forEach(function (part) { urls[part.number] = part.url; });
                return urls[number];
            });
        }

        function putPart(number, attempt) {
            var start = (number - 1) * partSize;
            var blob = file.slice(start, Math.min(start + partSize, file.size));
            return urlFor(number).then(function (url) {
                return new Promise(function (resolve, reject) {
                    var xhr = new XMLHttpRequest();
                    xhr.open("PUT", url, true);
                    xhr.upload.onprogress = function (event) {
                        if (event.lengthComputable) {
                            inFlight[number] = event.loaded;
                            report();
                        }
                    };
                    xhr.onload = function () {
                        var etag = xhr.getResponseHeader("ETag");
                        if (xhr.status >= 200 && xhr.status < 300 && etag) {
                            resolve(etag);
                        } else if (xhr.status >= 200 && xhr.status < 300) {
                            reject(new Error("The bucket did not return the part's ETag (check its CORS rule)."));
                        } else {
                            reject(new Error("The bucket answered " + xhr.status + " for part " + number + "."));
                        }
                    };
                    xhr.onerror = function () { reject(new Error("The connection dropped on part " + number + ".")); };
                    xhr.onabort = function () { reject(new Error("cancelled")); };
                    self.currentXhr = xhr;
                    xhr.send(blob);
                });
            }).then(function (etag) {
                etags[number] = etag;
                delete inFlight[number];
                doneBytes += blob.size;
                report();
            }, function (error) {
                delete inFlight[number];
                if (self.cancelled) { throw error; }
                if (attempt < RETRIES) {
                    // A presigned URL may have expired along with the connection;
                    // fetch a fresh batch before the next try.
                    delete urls[number];
                    return sleep(Math.min(30000, 1000 * Math.pow(2, attempt))).then(function () {
                        return putPart(number, attempt + 1);
                    });
                }
                throw error;
            });
        }

        function worker() {
            if (self.cancelled) { return Promise.reject(new Error("cancelled")); }
            while (next <= total && etags[next]) { next += 1; }
            if (next > total) { return Promise.resolve(); }
            var number = next;
            next += 1;
            return putPart(number, 0).then(worker);
        }

        var workers = [];
        for (var i = 0; i < CONCURRENCY; i += 1) { workers.push(worker()); }
        return Promise.all(workers).then(function () {
            self.say("Finishing up…");
            var parts = Object.keys(etags).map(function (number) {
                return {number: Number(number), etag: etags[number]};
            });
            return self.api("POST", self.urlFor(upload.upload, "complete/"), {parts: parts});
        });
    };

    Panel.prototype.cancel = function () {
        if (!this.running) { return; }
        this.cancelled = true;
        if (this.currentXhr) { this.currentXhr.abort(); }
        var saved = this.remembered();
        if (saved) {
            this.api("POST", this.urlFor(saved.upload, "abort/")).catch(function () {});
        }
        this.forget();
        this.busy(false);
        this.say("Upload cancelled.", "text-secondary");
        this.showResume();
    };

    document.querySelectorAll("[data-upload-panel]").forEach(function (root) {
        new Panel(root);
    });
})();
