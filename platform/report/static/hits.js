// The canary hits participant page (spec *Participant page*; decisions 6, 10; plan ruling 8):
// opens the event stream the service renders (GET /reports/<id>/hits/events), inserts each new
// hit's server-rendered HTML (hits_view.hit_html, carried on the event: ruling 8 - one renderer,
// so this script holds no template to drift from it), keeps the headline counts, the status line
// and an empty placeholder's text live, and offers "Notify me" and "Group by run". No inline script (CSP: script-src
// 'self'): everything here is this file, loaded with <script src>.
(function () {
  "use strict";
  var section = document.getElementById("hits");
  if (!section) return;
  var wid = section.dataset.wid;
  var initialLast = parseInt(section.dataset.last, 10) || 0;
  var list = section.querySelector(".hit-list");
  var headline = section.querySelector(".headline");
  var leaksEl = headline ? headline.querySelector(".leaks") : null;
  var perKindEl = headline ? headline.querySelector(".per-kind") : null;
  var statusEl = document.getElementById("hits-status");
  if (!wid || !list) return;

  // The quiet kinds' headline labels (hits_view.QUIET_LABELS) and their order (hits_view.QUIET_KINDS
  // then OTHER_LABEL): a presentational mirror, not a security boundary - the kind itself always
  // comes from the server-rendered html. hits_view.py carries a matching comment: the two change
  // together.
  var QUIET_LABELS = { seen: "metadata", args: "args", prompt: "prompt" };
  var QUIET_LABEL_ORDER = ["metadata", "args", "prompt", "other"];

  // The model this script keeps in sync with the DOM: every hit currently shown, newest first,
  // loud (top of the list) and quiet (inside "also seen") kept apart so grouping only touches
  // the loud ones (the mockup groups the main list; "also seen" stays one collapsed count).
  var loudHits = toArray(list.querySelectorAll(":scope > details.hit"));
  var alsoSeenInit = list.querySelector(":scope > details.also-seen");
  var quietHits = alsoSeenInit ? toArray(alsoSeenInit.querySelectorAll(":scope > details.hit")) : [];
  // Ids are hits-file line numbers, and the watcher only appends to that file (never truncates or
  // replaces it), so an id seen once is never reused: a plain set is enough, no eviction needed.
  var seenIds = {};
  loudHits.concat(quietHits).forEach(function (el) { seenIds[el.dataset.id] = true; });
  var grouping = false;

  function toArray(nodeList) {
    return Array.prototype.slice.call(nodeList);
  }

  // --- the event stream -------------------------------------------------------------------

  // "/reports/" is the service's own prefix (every route of it, the Coder app's URL), not a guess
  // at where this page happens to be served from.
  var es = new EventSource("/reports/" + wid + "/hits/events?after=" + initialLast);
  es.addEventListener("hit", function (ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (seenIds[data.id]) return; // a reconnect may resend what the catch-up already placed
    seenIds[data.id] = true;
    addHit(data);
  });
  es.addEventListener("status", function (ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return; // a malformed status event leaves the line and placeholder as they were
    }
    if (statusEl) statusEl.textContent = data.line;
    if (typeof data.empty === "string") {
      // No placeholder (the encrypted notice, or a hit already shown): nothing to update.
      var p = list.querySelector(":scope > p.placeholder");
      if (p) p.textContent = data.empty;
    }
  });
  // No onerror handling that closes the stream: EventSource reconnects on its own, with
  // Last-Event-ID (or this URL's ?after= on the very first connection).

  // --- inserting a hit ---------------------------------------------------------------------

  function parseHtml(html) {
    var tmp = document.createElement("template");
    tmp.innerHTML = html; // the one place this script trusts markup: the server's own (ruling 8)
    return tmp.content.firstElementChild;
  }

  function removePlaceholder() {
    // Only NO_HITS/NOT_WATCHED carries this class (hits_view.participant_body); the encrypted
    // notice is also a `p.muted` but stays once a hit cannot change it.
    var p = list.querySelector(":scope > p.placeholder");
    if (p) p.remove();
  }

  function addHit(data) {
    var el = parseHtml(data.html);
    if (!el) return;
    el.classList.add("new");
    removePlaceholder();
    if (data.loud) {
      loudHits.unshift(el);
      layoutLoud();
      bumpLeaks(data.kind);
    } else {
      quietHits.unshift(el);
      insertQuiet(el, data.kind);
    }
    if (data.loud && notifyEnabled && data.id > initialLast) {
      notify(data.kind, data.type);
    }
  }

  function insertQuiet(el, kind) {
    var block = ensureAlsoSeen();
    var summary = block.querySelector(":scope > summary");
    block.insertBefore(el, summary.nextSibling);
    bumpAlsoSeenSummary(summary);
    bumpAlsoSeenHeadline(kind);
  }

  function ensureAlsoSeen() {
    var block = list.querySelector(":scope > details.also-seen");
    if (block) return block;
    block = document.createElement("details");
    block.className = "also-seen";
    var summary = document.createElement("summary");
    summary.textContent = "also seen (0)";
    block.appendChild(summary);
    list.appendChild(block);
    return block;
  }

  // --- headline counts: bumped in place, no re-render of the server's text ------------------

  function bumpLeaks(kind) {
    if (!leaksEl) return;
    var m = /^(\d+)/.exec(leaksEl.textContent);
    var n = (m ? parseInt(m[1], 10) : 0) + 1;
    leaksEl.textContent = n + " leak" + (n === 1 ? "" : "s");
    if (!perKindEl || !kind) return;
    var parts = perKindEl.textContent.split(" · ");
    for (var i = 0; i < parts.length; i++) {
      var bits = parts[i].split(" ");
      if (bits[0] === kind) {
        bits[1] = String((parseInt(bits[1], 10) || 0) + 1);
        parts[i] = bits.join(" ");
        perKindEl.textContent = parts.join(" · ");
        return;
      }
    }
  }

  function bumpAlsoSeenSummary(summary) {
    var m = /\((\d+)\)/.exec(summary.textContent);
    var n = (m ? parseInt(m[1], 10) : 0) + 1;
    summary.textContent = "also seen (" + n + ")";
  }

  function bumpAlsoSeenHeadline(kind) {
    if (!headline) return;
    var label = QUIET_LABELS[kind] || "other";
    var el = headline.querySelector(".also-seen");
    if (!el) {
      el = document.createElement("span");
      el.className = "also-seen";
      el.textContent = "also seen: 1 (" + label + ")";
      headline.appendChild(el);
      return;
    }
    var m = /^also seen: (\d+) \(([^)]*)\)$/.exec(el.textContent);
    if (!m) return;
    var n = parseInt(m[1], 10) + 1;
    var labels = m[2] ? m[2].split(", ") : [];
    if (labels.indexOf(label) === -1) labels.push(label);
    labels.sort(function (a, b) { return QUIET_LABEL_ORDER.indexOf(a) - QUIET_LABEL_ORDER.indexOf(b); });
    el.textContent = "also seen: " + n + " (" + labels.join(", ") + ")";
  }

  // --- "Group by run": reorders the server's own elements, builds no HTML -------------------

  function hitKey(el) {
    return (el.dataset.session || "") + "␟" + (el.dataset.run || "");
  }

  function removeHeadings() {
    toArray(list.querySelectorAll(":scope > .hit-group-heading")).forEach(function (h) { h.remove(); });
  }

  function anchor() {
    return list.querySelector(":scope > details.also-seen") || null;
  }

  function layoutFlat() {
    removeHeadings();
    var at = anchor();
    loudHits.forEach(function (el) { list.insertBefore(el, at); });
  }

  function layoutGrouped() {
    removeHeadings();
    var at = anchor();
    var order = [];
    var groups = {};
    loudHits.forEach(function (el) {
      var key = hitKey(el);
      if (!groups[key]) {
        groups[key] = { session: el.dataset.session, run: el.dataset.run, items: [] };
        order.push(key);
      }
      groups[key].items.push(el);
    });
    order.forEach(function (key) {
      var g = groups[key];
      var heading = document.createElement("div");
      heading.className = "hit-group-heading";
      heading.textContent = (g.session ? "session " + g.session : "session —")
        + (g.run ? " · run " + g.run : "");
      list.insertBefore(heading, at);
      g.items.forEach(function (el) { list.insertBefore(el, at); });
    });
  }

  function layoutLoud() {
    if (grouping) layoutGrouped(); else layoutFlat();
  }

  var groupBtn = document.getElementById("group-toggle");
  if (groupBtn) {
    groupBtn.hidden = false;
    groupBtn.addEventListener("click", function () {
      grouping = !grouping;
      groupBtn.textContent = grouping ? "Newest first" : "Group by run";
      layoutLoud();
    });
  }

  // --- "Notify me": kind and type only, never the value or excerpt (decision 10) ------------

  var notifyBtn = document.getElementById("notify-btn");
  var notifyEnabled = false;

  function notify(kind, type) {
    try {
      new Notification("Canary hit: " + kind, { body: type || "" });
    } catch (e) {
      // notifications are a convenience; a browser that refuses them still has the page
    }
  }

  if (notifyBtn && "Notification" in window) {
    notifyBtn.hidden = false;
    if (Notification.permission === "granted") {
      notifyEnabled = true;
      notifyBtn.textContent = "Notifications on";
      notifyBtn.disabled = true;
    } else if (Notification.permission === "denied") {
      // Already refused (e.g. by the browser's own prompt earlier): no button that asks again
      // and does nothing.
      notifyBtn.textContent = "Notifications blocked";
      notifyBtn.disabled = true;
    } else {
      notifyBtn.textContent = "Notify me";
      notifyBtn.addEventListener("click", function () {
        Notification.requestPermission().then(function (permission) {
          if (permission === "granted") {
            notifyEnabled = true;
            notifyBtn.textContent = "Notifications on";
            notifyBtn.disabled = true;
          } else if (permission === "denied") {
            notifyBtn.textContent = "Notifications blocked";
            notifyBtn.disabled = true;
          }
        });
      });
    }
  }
})();
