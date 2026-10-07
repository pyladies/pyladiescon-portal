/* PyLadiesCon program widget, v1 (design §11.2). No dependencies.
 *
 *   <div data-pyladiescon-widget="schedule" data-conference="2026"></div>
 *   <script src="https://<portal>/static/widget/v1.js" defer></script>
 *
 * Views: schedule (default), speakers, session (with data-session="<slug>").
 * Optional: data-api (portal origin, defaults to this script's),
 * data-preview (or ?preview= on the host page), data-fallback-url.
 * Restyle through the --plc-* CSS variables on .plc. */
(function () {
  "use strict";
  var me = document.currentScript;
  var ORIGIN = me ? new URL(me.src, location.href).origin : "";
  var CSS = ".plc{--plc-accent:#8a1e5b;--plc-muted:#5f5f6b;--plc-border:#d9d9e0;--plc-band:#f3eef6;--plc-card:transparent;--plc-radius:8px;font:inherit;color:inherit}" +
    ".plc *{box-sizing:border-box}.plc a{color:var(--plc-accent)}" +
    ".plc-bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 .75rem}" +
    ".plc-bar select{font:inherit;max-width:100%}" +
    ".plc-tab{font:inherit;border:1px solid var(--plc-border);background:none;color:inherit;border-radius:999px;padding:.25rem .8rem;cursor:pointer}" +
    ".plc-tab[aria-selected=true]{background:var(--plc-accent);border-color:var(--plc-accent);color:#fff}" +
    ".plc-list{display:grid;gap:.5rem}" +
    ".plc-card{border:1px solid var(--plc-border);border-radius:var(--plc-radius);padding:.75rem;background:var(--plc-card)}" +
    ".plc-band{background:var(--plc-band);border-radius:var(--plc-radius);padding:.4rem .75rem;color:var(--plc-muted);display:flex;flex-wrap:wrap;gap:.25rem .75rem}" +
    ".plc-meta{color:var(--plc-muted);font-size:.875em}.plc-title{font-weight:600;margin:.15rem 0}" +
    ".plc-row{display:flex;flex-wrap:wrap;gap:.5rem .9rem;align-items:center;margin-top:.5rem;font-size:.875em}" +
    ".plc-star{font:inherit;background:none;border:0;padding:0;cursor:pointer;color:var(--plc-accent);font-size:1.15em;line-height:1}" +
    ".plc details>summary{cursor:pointer;color:var(--plc-accent)}" +
    ".plc-grid{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))}" +
    ".plc-person{display:flex;gap:.75rem;align-items:flex-start}" +
    ".plc-photo{width:4rem;height:4rem;border-radius:50%;object-fit:cover;flex:none}" +
    ".plc-note{padding:1rem;border:1px dashed var(--plc-border);border-radius:var(--plc-radius);text-align:center}";

  function load(key) {
    try { return JSON.parse(localStorage.getItem("plc:" + key)); } catch (e) { return null; }
  }
  function keep(key, value) {
    try { localStorage.setItem("plc:" + key, JSON.stringify(value)); } catch (e) { /* private mode */ }
  }

  /* Element builder. Text always goes in as text; "html" is only ever a
   * *_html field, which the portal sanitizes. */
  function h(tag, props, kids) {
    var el = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === "html") el.innerHTML = v;
      else if (k === "text") el.textContent = v;
      else if (k.indexOf("on") === 0) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    [].concat(kids || []).forEach(function (c) {
      if (c != null && c !== "") el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return el;
  }

  /* replaceChildren would print a missing piece as the text "null". */
  function fill(el, kids) {
    el.replaceChildren.apply(el, kids.filter(Boolean));
  }

  function parts(date, tz) {
    var out = {};
    new Intl.DateTimeFormat("en-CA", {
      timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    }).formatToParts(date).forEach(function (p) { out[p.type] = p.value; });
    return out;
  }
  function dayOf(iso, tz) {
    var p = parts(new Date(iso), tz);
    return p.year + "-" + p.month + "-" + p.day;
  }
  function time(iso, tz) {
    return new Intl.DateTimeFormat(undefined, { timeZone: tz, hour: "numeric", minute: "2-digit" }).format(new Date(iso));
  }
  function dayLabel(key) {
    return new Date(key + "T12:00:00Z").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  }

  /* Subscribe, never download: a subscribed calendar follows a reschedule. */
  function calendar(url, name, label) {
    var webcal = url.replace(/^https?:/, "webcal:");
    var e = encodeURIComponent;
    return h("details", {}, [
      h("summary", { text: label }),
      h("div", { "class": "plc-row" }, [
        h("a", { href: webcal, text: "Apple / Outlook desktop" }),
        h("a", { href: "https://calendar.google.com/calendar/r?cid=" + e(webcal), target: "_blank", rel: "noopener", text: "Google" }),
        h("a", { href: "https://outlook.live.com/calendar/0/addfromweb?url=" + e(url) + "&name=" + e(name), target: "_blank", rel: "noopener", text: "Outlook.com" })
      ])
    ]);
  }

  function Widget(el) {
    var d = el.dataset;
    var base = (d.api || ORIGIN).replace(/\/$/, "");
    this.el = el;
    this.view = d.pyladiesconWidget || "schedule";
    this.conf = d.conference || "";
    this.slug = d.session || "";
    this.api = base + "/api/v1/" + encodeURIComponent(this.conf) + "/";
    this.preview = d.preview || new URLSearchParams(location.search).get("preview");
    this.fallback = d.fallbackUrl || base + "/embed/" + encodeURIComponent(this.conf) + "/schedule/";
    this.browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    this.tz = load("tz") || this.browserTz;
    this.stars = load("stars:" + this.conf) || [];
    el.classList.add("plc");
    this.note("Loading the program…");
    this.fetch();
  }

  Widget.prototype.note = function (text, link) {
    fill(this.el, [h("div", { "class": "plc-note" }, [text, link ? " " : null, link])]);
  };

  Widget.prototype.fetch = function () {
    var self = this;
    var path = this.view === "speakers" ? "presenters/" :
      this.view === "session" ? "sessions/" + encodeURIComponent(this.slug) + "/" : "sessions/";
    var url = this.api + path + (this.preview ? "?preview=" + encodeURIComponent(this.preview) : "");
    fetch(url, { credentials: "omit" })
      .then(function (r) {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then(function (data) { self.data = data; self.render(); })
      .catch(function () {
        self.note("The program can't load right now.", h("a", { href: self.fallback, text: "See it on the PyLadiesCon portal." }));
      });
  };

  Widget.prototype.render = function () {
    var data = this.data;
    var empty = this.view === "speakers" ? !data.presenters.length :
      this.view === "session" ? !data.session : !data.sessions.length;
    if (data.program === "internal" || empty) {
      this.note(data.program === "internal" ? "Program coming soon." : "Nothing here yet.");
      return;
    }
    if (this.view === "speakers") this.renderSpeakers();
    else if (this.view === "session") fill(this.el, [this.zones(), this.card(data.session, true)]);
    else this.renderSchedule();
  };

  Widget.prototype.zones = function () {
    var self = this;
    var own = this.data.conference.timezone;
    var list = [this.browserTz, own, "UTC", this.tz];
    if (Intl.supportedValuesOf) list = list.concat(Intl.supportedValuesOf("timeZone"));
    var seen = {};
    var select = h("select", {
      "aria-label": "Timezone",
      onchange: function () {
        self.tz = select.value;
        keep("tz", self.tz);
        self.render();
      }
    }, list.filter(function (z) { return z && !seen[z] && (seen[z] = true); }).map(function (z) {
      var label = z + (z === self.browserTz ? " (yours)" : z === own ? " (conference)" : "");
      return h("option", { value: z, selected: z === self.tz, text: label });
    }));
    return h("div", { "class": "plc-bar" }, [h("label", { "class": "plc-meta", text: "Times in" }), select]);
  };

  Widget.prototype.renderSchedule = function () {
    var self = this;
    var tz = this.tz;
    var days = {};
    this.data.sessions.forEach(function (s) {
      var key = dayOf(s.slot.start, tz);
      (days[key] = days[key] || []).push(s);
    });
    var keys = Object.keys(days).sort();
    if (keys.indexOf(this.day) < 0) this.day = keys[0];
    var tabs = h("div", { "class": "plc-bar", role: "tablist" }, keys.map(function (key) {
      return h("button", {
        type: "button", role: "tab", "class": "plc-tab", "aria-selected": String(key === self.day),
        text: dayLabel(key), onclick: function () { self.day = key; self.render(); }
      });
    }));
    var list = h("div", { "class": "plc-list", role: "tabpanel" }, days[this.day].map(function (s) {
      return s.is_content ? self.card(s, false) : h("div", { "class": "plc-band" }, [
        h("span", { text: time(s.slot.start, tz) + "–" + time(s.slot.end, tz) }),
        h("strong", { text: s.title })
      ]);
    }));
    fill(this.el, [this.zones(), tabs, this.starBar(), list]);
  };

  Widget.prototype.starBar = function () {
    var picked = this.stars.filter(function (slug) {
      return this.data.sessions.some(function (s) { return s.slug === slug; });
    }, this);
    if (!picked.length) return null;
    var url = this.api + "schedule.ics?sessions=" + picked.map(encodeURIComponent).join(",");
    return h("div", { "class": "plc-bar plc-meta" }, [
      "★ " + picked.length + " starred.",
      calendar(url, "PyLadiesCon: my sessions", "Add your starred sessions to your calendar")
    ]);
  };

  Widget.prototype.card = function (s, full) {
    var self = this;
    var tz = this.tz;
    var starred = this.stars.indexOf(s.slug) >= 0;
    var text = ["summary", "outline", "prerequisites", "audience"].filter(function (k) {
      return s[k + "_html"];
    });
    var body = text.map(function (k) {
      return h("div", {}, [k === "summary" ? null : h("div", { "class": "plc-meta", text: k[0].toUpperCase() + k.slice(1) }), h("div", { html: s[k + "_html"] })]);
    });
    return h("article", { "class": "plc-card" }, [
      h("div", { "class": "plc-meta" }, [
        (full ? dayLabel(dayOf(s.slot.start, tz)) + ", " : "") + time(s.slot.start, tz) + "–" + time(s.slot.end, tz),
        " · " + s.kind.name,
        s.slot.room ? " · " + s.slot.room.name : null
      ]),
      h("div", { "class": "plc-title", text: s.title }),
      s.presenters.length ? h("div", { text: s.presenters.map(function (p) { return p.name; }).join(", ") }) : null,
      full ? h("div", {}, body) : body.length ? h("details", {}, [h("summary", { text: "About this session" })].concat(body)) : null,
      h("div", { "class": "plc-row" }, [
        full ? null : h("button", {
          type: "button", "class": "plc-star", "aria-pressed": String(starred),
          "aria-label": (starred ? "Unstar " : "Star ") + s.title,
          text: starred ? "★" : "☆",
          onclick: function () { self.toggle(s.slug); }
        }),
        s.youtube_url ? h("a", { href: s.youtube_url, target: "_blank", rel: "noopener", text: "Watch" }) : null,
        calendar(s.urls.ics, s.title, "Add to calendar")
      ])
    ]);
  };

  Widget.prototype.toggle = function (slug) {
    var at = this.stars.indexOf(slug);
    if (at >= 0) this.stars.splice(at, 1); else this.stars.push(slug);
    keep("stars:" + this.conf, this.stars);
    this.render();
  };

  Widget.prototype.renderSpeakers = function () {
    var links = { website: "Website", github: "GitHub", mastodon: "Mastodon", linkedin: "LinkedIn", bluesky: "Bluesky" };
    var profile = { github: "https://github.com/", bluesky: "https://bsky.app/profile/" };
    fill(this.el, [h("div", { "class": "plc-grid" }, this.data.presenters.map(function (p) {
      var found = Object.keys(links).filter(function (k) { return p.links[k]; });
      return h("article", { "class": "plc-card" }, [
        h("div", { "class": "plc-person" }, [
          p.headshot_url ? h("img", { "class": "plc-photo", src: p.headshot_url, alt: "", loading: "lazy" }) : null,
          h("div", {}, [
            h("div", { "class": "plc-title", text: p.name }),
            p.pronouns ? h("div", { "class": "plc-meta", text: p.pronouns }) : null,
            h("div", { "class": "plc-meta", text: p.sessions.map(function (s) { return s.title; }).join(" · ") })
          ])
        ]),
        p.bio_html ? h("details", {}, [h("summary", { text: "Bio" }), h("div", { html: p.bio_html })]) : null,
        found.length ? h("div", { "class": "plc-row" }, found.map(function (k) {
          return h("a", { href: (profile[k] || "") + p.links[k], target: "_blank", rel: "noopener me", text: links[k] });
        })) : null
      ]);
    }))]);
  };

  function start() {
    if (!document.getElementById("plc-style")) {
      document.head.appendChild(h("style", { id: "plc-style", text: CSS }));
    }
    document.querySelectorAll("[data-pyladiescon-widget]").forEach(function (el) {
      if (!el.plcWidget) el.plcWidget = new Widget(el);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
