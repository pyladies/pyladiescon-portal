/* PyLadiesCon program widget, v1 (design §11.2). No dependencies.
 *
 * This is the readable source. The portal serves the minified build in
 * portal/static/widget/v1.js; run `npm run build:widget` after any change.
 * Usage and options: speakers/README.md.
 *
 * Views: schedule (default), sessions, speakers, session
 * (data-session="<slug>"), speaker (data-speaker="<slug>"). Session titles and speaker names open
 * an overlay with the details. */
(function () {
  "use strict";
  var me = document.currentScript;
  var ORIGIN = me ? new URL(me.src, location.href).origin : "";
  var STEP = 5; /* grid rows, in minutes */
  var CSS = [
    ".plc{--plc-accent:#8a1e5b;--plc-muted:#5f5f6b;--plc-border:#d9d9e0;--plc-band:#f3eef6;--plc-card:Canvas;--plc-radius:8px;--plc-modal-bg:#fff;--plc-modal-text:#1f1f24;font:inherit;color:inherit}",
    ".plc *{box-sizing:border-box}.plc a{color:var(--plc-accent)}",
    ".plc-bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 .75rem}",
    ".plc select{font:inherit;max-width:100%}",
    ".plc-tab{font:inherit;border:1px solid var(--plc-border);background:none;color:inherit;border-radius:999px;padding:.25rem .8rem;cursor:pointer}",
    ".plc-tab[aria-selected=true]{background:var(--plc-accent);border-color:var(--plc-accent);color:#fff}",
    ".plc-sched{container-type:inline-size}",
    /* No row gap: a day has hundreds of five-minute rows. A small
     * minimum height keeps an empty stretch visible, and lines every 15
     * minutes (darker on the hour) say where it starts and ends. Items
     * space themselves; cards sit above the lines. */
    ".plc-grid{display:grid;column-gap:.5rem;grid-auto-rows:minmax(.2rem,auto)}",
    ".plc-line{border-top:1px dashed var(--plc-border);height:0;margin:0!important;align-self:start;opacity:.6}",
    ".plc-hour{border-top-style:solid;opacity:1}",
    ".plc-card,.plc-band{position:relative;z-index:1}",
    ".plc-grid>*{margin-bottom:.4rem}",
    ".plc-head{font-weight:600;font-size:.875em;color:var(--plc-muted);padding-bottom:.25rem}",
    ".plc-time{font-size:.8em;color:var(--plc-muted);white-space:nowrap;line-height:1;transform:translateY(-.4em);margin:0!important}",
    "@container (max-width:40rem){.plc-grid{display:flex;flex-direction:column}.plc-head,.plc-time,.plc-line{display:none}}",
    ".plc-card{border:1px solid var(--plc-border);border-radius:var(--plc-radius);padding:.6rem .7rem;background:var(--plc-card);min-width:0}",
    ".plc-band{background:var(--plc-band);border-radius:var(--plc-radius);padding:.4rem .7rem;color:var(--plc-muted);display:flex;flex-wrap:wrap;gap:.25rem .75rem;align-items:center}",
    ".plc-meta{color:var(--plc-muted);font-size:.85em}",
    ".plc-link{font:inherit;font-weight:600;background:none;border:0;padding:0;margin:.15rem 0;color:inherit;text-align:left;cursor:pointer}",
    ".plc-link:hover,.plc-who:hover span{text-decoration:underline}",
    ".plc-people{display:flex;flex-wrap:wrap;gap:.35rem .75rem;margin-top:.35rem}",
    ".plc-who{display:inline-flex;align-items:center;gap:.4rem;font:inherit;font-size:.9em;background:none;border:0;padding:0;color:inherit;text-align:left}",
    "button.plc-who{cursor:pointer}",
    ".plc-av{width:1.75rem;height:1.75rem;border-radius:50%;object-fit:cover;flex:none;background:var(--plc-band);display:inline-flex;align-items:center;justify-content:center;font-size:.7em;font-weight:600;color:var(--plc-muted)}",
    /* Initials stand in for a missing photo: a tint of the accent, so
     * they stay visible on a white card and on a band alike. */
    ".plc-ini{background:#ead6e3;background:color-mix(in srgb,var(--plc-accent) 18%,#fff);color:var(--plc-accent);box-shadow:inset 0 0 0 1px var(--plc-border)}",
    ".plc-big{width:5rem;height:5rem;font-size:1.4em}",
    ".plc-row{display:flex;flex-wrap:wrap;gap:.5rem .9rem;align-items:center;margin-top:.6rem;font-size:.9em}",
    ".plc details>summary{cursor:pointer;color:var(--plc-accent)}",
    ".plc-list{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))}",
    ".plc-person{display:flex;gap:.75rem;align-items:center}",
    ".plc-note{padding:1rem;border:1px dashed var(--plc-border);border-radius:var(--plc-radius);text-align:center}",
    ".plc-modal{border:0;border-radius:var(--plc-radius);padding:1.25rem;width:min(40rem,calc(100% - 2rem));max-height:calc(100% - 2rem);background:var(--plc-modal-bg);color:var(--plc-modal-text)}",
    ".plc-modal::backdrop{background:rgba(20,20,30,.5)}",
    ".plc-modal h2{font-size:1.25em;margin:.2rem 2rem .4rem 0}",
    ".plc-close{position:absolute;top:.6rem;right:.7rem;font:inherit;font-size:1.4em;line-height:1;background:none;border:0;cursor:pointer;color:inherit}",
    ".plc-sub{font-weight:600;margin:.9rem 0 .2rem}"
  ].join("");

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
      else if (k === "style") el.style.cssText = v;
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
  function span(slot, tz, withDay) {
    return (withDay ? dayLabel(dayOf(slot.start, tz)) + ", " : "") + time(slot.start, tz) + "–" + time(slot.end, tz);
  }
  function minutes(a, b) {
    return Math.round((new Date(b) - new Date(a)) / 60000);
  }

  function avatar(person, big) {
    var cls = "plc-av" + (big ? " plc-big" : "");
    if (person.headshot_url) return h("img", { "class": cls, src: person.headshot_url, alt: "", loading: "lazy" });
    var initials = person.name.split(/\s+/).map(function (w) { return w.charAt(0); }).join("").slice(0, 2).toUpperCase();
    return h("span", { "class": cls + " plc-ini", "aria-hidden": "true", text: initials });
  }

  /* Subscribe, never download: a subscribed calendar follows a reschedule. */
  function calendar(url, name) {
    var webcal = url.replace(/^https?:/, "webcal:");
    var e = encodeURIComponent;
    return h("details", {}, [
      h("summary", { text: "Add to calendar" }),
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
    this.slug = d.session || d.speaker || "";
    this.api = base + "/api/v1/" + encodeURIComponent(this.conf) + "/";
    this.preview = d.preview || new URLSearchParams(location.search).get("preview");
    this.fallback = d.fallbackUrl || base + "/embed/" + encodeURIComponent(this.conf) + "/schedule/";
    this.browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    this.tz = load("tz") || this.browserTz;
    this.room = load("room:" + this.conf) || "";
    this.people = {};
    el.classList.add("plc");
    this.note("Loading the program…");
    this.start();
  }

  Widget.prototype.get = function (path) {
    var url = this.api + path + (this.preview ? "?preview=" + encodeURIComponent(this.preview) : "");
    return fetch(url, { credentials: "omit" }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    });
  };

  Widget.prototype.note = function (text, link) {
    fill(this.el, [h("div", { "class": "plc-note" }, [text, link ? " " : null, link])]);
  };

  Widget.prototype.start = function () {
    var self = this;
    var e = encodeURIComponent;
    var path = {
      speakers: "presenters/",
      session: "sessions/" + e(this.slug) + "/",
      speaker: "presenters/" + e(this.slug) + "/"
    }[this.view] || "sessions/";
    this.get(path)
      .then(function (data) { self.data = data; self.render(); })
      .catch(function () {
        self.note("The program can't load right now.", h("a", { href: self.fallback, text: "See it on the PyLadiesCon portal." }));
      });
  };

  Widget.prototype.render = function () {
    var data = this.data;
    var self = this;
    var list = data.sessions || data.presenters;
    var one = data.session || data.presenter;
    if (data.program === "internal" || (list ? !list.length : !one)) {
      this.note(data.program === "internal" ? "Program coming soon." : "Nothing here yet.");
      return;
    }
    if (data.sessions) {
      this.bySlug = {};
      data.sessions.forEach(function (s) { self.bySlug[s.slug] = s; });
    }
    if (this.view === "speakers") this.renderSpeakers();
    else if (this.view === "sessions") this.renderSessions();
    else if (this.view === "session") fill(this.el, [this.zones()].concat(this.sessionDetail(one)));
    else if (this.view === "speaker") fill(this.el, [this.zones()].concat(this.speakerDetail(one)));
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

  /* People on a session: photo and name, a button when they have a profile. */
  Widget.prototype.who = function (presenters) {
    var self = this;
    if (!presenters.length) return null;
    return h("div", { "class": "plc-people" }, presenters.map(function (p) {
      var kids = [avatar(p), h("span", { text: p.name })];
      return p.slug ? h("button", {
        type: "button", "class": "plc-who", "aria-label": "About " + p.name,
        onclick: function () { self.openSpeaker(p.slug); }
      }, kids) : h("span", { "class": "plc-who" }, kids);
    }));
  };

  Widget.prototype.title = function (s) {
    var self = this;
    return h("button", { type: "button", "class": "plc-link", text: s.title, onclick: function () { self.openSession(s); } });
  };

  Widget.prototype.renderSchedule = function () {
    var self = this;
    var tz = this.tz;
    var days = {};
    var rooms = [];
    this.data.sessions.forEach(function (s) {
      var key = dayOf(s.slot.start, tz);
      (days[key] = days[key] || []).push(s);
      var name = s.slot.room && s.slot.room.name;
      if (name && rooms.indexOf(name) < 0) rooms.push(name);
    });
    rooms.sort();
    if (rooms.indexOf(this.room) < 0) this.room = "";
    var keys = Object.keys(days).sort();
    if (keys.indexOf(this.day) < 0) this.day = keys[0];
    var tabs = h("div", { "class": "plc-bar", role: "tablist" }, keys.map(function (key) {
      return h("button", {
        type: "button", role: "tab", "class": "plc-tab", "aria-selected": String(key === self.day),
        text: dayLabel(key), onclick: function () { self.day = key; self.render(); }
      });
    }));
    var columns = this.room ? [this.room] : rooms.length ? rooms : [""];
    var shown = days[this.day].filter(function (s) {
      return !s.slot.room || columns.indexOf(s.slot.room.name) >= 0;
    }).sort(function (a, b) {
      return a.slot.start < b.slot.start ? -1 : a.slot.start > b.slot.start ? 1 :
        columns.indexOf(a.slot.room && a.slot.room.name) - columns.indexOf(b.slot.room && b.slot.room.name);
    });
    /* The grid: a time column, then a column per room; rows are STEP
     * minutes from the day's first start. Bands span every room. Below
     * 40rem the container query turns it into a plain list. */
    /* Rows count from the quarter hour before the first start, so every
     * tick lands on a row; offsets are whole quarters in every zone. */
    var Q = 15 * 60000;
    var first = new Date(Math.floor(new Date(shown.reduce(function (min, s) {
      return s.slot.start < min ? s.slot.start : min;
    }, shown[0].slot.start)) / Q) * Q).toISOString();
    var last = shown.reduce(function (max, s) { return s.slot.end > max ? s.slot.end : max; }, shown[0].slot.end);
    function row(iso) { return 2 + Math.floor(minutes(first, iso) / STEP); }
    var cells = [];
    if (columns[0]) {
      columns.forEach(function (name, i) {
        cells.push(h("div", { "class": "plc-head", style: "grid-row:1;grid-column:" + (i + 2), text: name }));
      });
    }
    shown.forEach(function (s) {
      var from = row(s.slot.start);
      var rows = Math.max(1, Math.round(minutes(s.slot.start, s.slot.end) / STEP));
      var column = s.slot.room ? columns.indexOf(s.slot.room.name) + 2 : 2;
      var place = "grid-row:" + from + " / span " + rows + ";grid-column:" + (s.slot.room ? column : "2 / -1");
      cells.push(s.is_content ? h("article", { "class": "plc-card", style: place }, [
        h("div", { "class": "plc-meta" }, [span(s.slot, tz), " · " + s.kind.name, s.slot.room ? " · " + s.slot.room.name : null]),
        self.title(s),
        self.who(s.presenters)
      ]) : h("div", { "class": "plc-band", style: place }, [
        h("span", { text: span(s.slot, tz) }),
        s.summary_html || s.presenters.length ? self.title(s) : h("strong", { text: s.title }),
        self.who(s.presenters)
      ]));
    });
    /* Ticks: a line every quarter hour, a label on the half hour, in
     * the visitor's zone. */
    for (var at = new Date(first).getTime(); at <= new Date(last).getTime(); at += Q) {
      var iso = new Date(at).toISOString();
      var minute = Number(parts(new Date(at), tz).minute);
      var tick = "grid-row:" + row(iso) + ";grid-column:";
      cells.unshift(h("div", { "class": "plc-line" + (minute ? "" : " plc-hour"), style: tick + "2 / -1" }));
      if (minute % 30 === 0) cells.unshift(h("div", { "class": "plc-time", style: tick + "1", text: time(iso, tz) }));
    }
    var grid = h("div", {
      "class": "plc-grid", role: "tabpanel",
      style: "grid-template-columns:auto repeat(" + columns.length + ",minmax(0,1fr))"
    }, cells);
    var top = this.zones();
    if (rooms.length > 1) {
      var picker = h("select", {
        "aria-label": "Room",
        onchange: function () {
          self.room = picker.value;
          keep("room:" + self.conf, self.room);
          self.render();
        }
      }, [h("option", { value: "", text: "All rooms" })].concat(rooms.map(function (name) {
        return h("option", { value: name, selected: name === self.room, text: name });
      })));
      top.appendChild(picker);
    }
    fill(this.el, [top, tabs, h("div", { "class": "plc-sched" }, [grid])]);
  };

  /* Every talk, panel and workshop as a card, in program order; a title
   * opens the overlay. Program items (breaks, keynotes) stay on the
   * schedule. */
  Widget.prototype.renderSessions = function () {
    var self = this;
    var tz = this.tz;
    fill(this.el, [this.zones(), h("div", { "class": "plc-list" }, this.data.sessions.filter(function (s) {
      return s.is_content;
    }).map(function (s) {
      return h("article", { "class": "plc-card" }, [
        h("div", { "class": "plc-meta" }, [span(s.slot, tz, true), " · " + s.kind.name, s.slot.room ? " · " + s.slot.room.name : null]),
        self.title(s),
        self.who(s.presenters)
      ]);
    }))]);
  };

  Widget.prototype.renderSpeakers = function () {
    var self = this;
    fill(this.el, [h("div", { "class": "plc-list" }, this.data.presenters.map(function (p) {
      self.people[p.slug] = p;
      return h("article", { "class": "plc-card" }, [
        h("button", {
          type: "button", "class": "plc-who plc-person", "aria-label": "About " + p.name,
          onclick: function () { self.openSpeaker(p.slug); }
        }, [avatar(p, true), h("span", {}, [
          h("strong", { text: p.name }),
          p.pronouns ? h("div", { "class": "plc-meta", text: p.pronouns }) : null
        ])]),
        h("div", { "class": "plc-meta", style: "margin-top:.4rem", text: p.sessions.map(function (s) { return s.title; }).join(" · ") })
      ]);
    }))]);
  };

  /* One session in full: the overlay, and the session view. */
  Widget.prototype.sessionDetail = function (s) {
    var labels = { outline: "Outline", prerequisites: "Before you come", audience: "Who it is for" };
    var tz = this.tz;
    return [
      h("div", { "class": "plc-meta" }, [span(s.slot, tz, true), " · " + s.kind.name, s.slot.room ? " · " + s.slot.room.name : null]),
      h("h2", { text: s.title }),
      this.who(s.presenters),
      s.summary_html ? h("div", { html: s.summary_html }) : null
    ].concat(["outline", "prerequisites", "audience"].map(function (k) {
      return s[k + "_html"] ? h("div", {}, [h("div", { "class": "plc-sub", text: labels[k] }), h("div", { html: s[k + "_html"] })]) : null;
    })).concat([h("div", { "class": "plc-row" }, [
      s.youtube_url ? h("a", { href: s.youtube_url, target: "_blank", rel: "noopener", text: "Watch" }) : null,
      calendar(s.urls.ics, s.title)
    ])]);
  };

  /* One speaker in full: the overlay, and the speaker view. */
  Widget.prototype.speakerDetail = function (p) {
    var self = this;
    var tz = this.tz;
    var links = { website: "Website", github: "GitHub", mastodon: "Mastodon", linkedin: "LinkedIn", bluesky: "Bluesky" };
    var profile = { github: "https://github.com/", bluesky: "https://bsky.app/profile/" };
    var found = Object.keys(links).filter(function (k) { return p.links[k]; });
    return [
      h("div", { "class": "plc-person" }, [avatar(p, true), h("div", {}, [
        h("h2", { text: p.name, style: "margin:0" }),
        h("div", { "class": "plc-meta", text: [p.pronouns, p.location].filter(Boolean).join(" · ") })
      ])]),
      p.bio_html ? h("div", { html: p.bio_html }) : null,
      found.length ? h("div", { "class": "plc-row" }, found.map(function (k) {
        return h("a", { href: (profile[k] || "") + p.links[k], target: "_blank", rel: "noopener me", text: links[k] });
      })) : null,
      p.sessions.length ? h("div", { "class": "plc-sub", text: "Sessions" }) : null
    ].concat(p.sessions.map(function (s) {
      var known = self.bySlug && self.bySlug[s.slug];
      return h("div", {}, [
        h("span", { "class": "plc-meta", text: span(s, tz, true) + " " }),
        known ? self.title(known) : h("span", { text: s.title })
      ]);
    }));
  };

  /* One overlay per widget: a native <dialog>, so Escape, focus and the
   * backdrop come from the browser. */
  Widget.prototype.open = function (kids) {
    var self = this;
    if (!this.dialog) {
      this.dialog = h("dialog", {
        "class": "plc plc-modal",
        onclick: function (event) { if (event.target === self.dialog) self.dialog.close(); }
      });
      document.body.appendChild(this.dialog);
    }
    fill(this.dialog, [h("button", {
      type: "button", "class": "plc-close", "aria-label": "Close", text: "×",
      onclick: function () { self.dialog.close(); }
    })].concat(kids));
    if (!this.dialog.open) this.dialog.showModal();
    this.dialog.scrollTop = 0;
  };

  Widget.prototype.openSession = function (s) {
    this.open(this.sessionDetail(s));
  };

  Widget.prototype.openSpeaker = function (slug) {
    var self = this;
    if (this.people[slug]) {
      this.open(this.speakerDetail(this.people[slug]));
      return;
    }
    this.open([h("p", { text: "Loading…" })]);
    this.get("presenters/" + encodeURIComponent(slug) + "/")
      .then(function (data) {
        self.people[slug] = data.presenter;
        self.open(self.speakerDetail(data.presenter));
      })
      .catch(function () { self.open([h("p", { text: "This profile can't load right now." })]); });
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
