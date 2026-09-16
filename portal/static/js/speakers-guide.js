// Speaker guide (templates/speakers/speaker_guide.html): record the read
// receipt when the reader reaches the end, without a page reload. The
// explicit "I've read this" button is the accessible fallback and also
// works with JavaScript off.
(function () {
    var form = document.getElementById("guide-read-form");
    if (!form || form.dataset.read === "true") {
        return;
    }
    var sent = false;
    function markRead() {
        if (sent) {
            return;
        }
        sent = true;
        fetch(form.action, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
                "X-Requested-With": "fetch",
            },
        }).then(function (response) {
            if (response.ok) {
                form.dataset.read = "true";
                var done = document.getElementById("guide-read-done");
                if (done) {
                    done.hidden = false;
                }
                form.hidden = true;
            }
        });
    }
    function nearEnd() {
        var doc = document.documentElement;
        return window.innerHeight + window.scrollY >= doc.scrollHeight - 40;
    }
    function onScroll() {
        if (nearEnd()) {
            window.removeEventListener("scroll", onScroll);
            markRead();
        }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    if (nearEnd()) {
        onScroll();
    }
})();
