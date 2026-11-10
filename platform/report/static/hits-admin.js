// The canary hits admin page (spec *Admin page*; decision 7): the four filters hide the hits that do
// not match, and the event stream over every workspace (GET /reports/hits/events) inserts each new
// hit at the top under the same filters and bumps its workspace's counts. The hit itself is the
// server's own HTML (hits_view.hit_html, carried on the event), and the count to bump is the cell
// whose data-kind says so (or the data-quiet one), as hits_view.admin_body renders them: this script
// keeps no list of kinds or labels of its own. On a reconnect it reloads the page, which reads the
// hits afresh (the stream does not resume). No inline script (CSP: script-src 'self').
(function () {
  "use strict";
  var list = document.getElementById("admin-hits");
  if (!list) return;
  var selects = Array.prototype.slice.call(document.querySelectorAll("select[data-filter]"));

  function toArray(nodeList) {
    return Array.prototype.slice.call(nodeList);
  }

  // --- filters ------------------------------------------------------------------------------

  function matches(el) {
    return selects.every(function (s) {
      return !s.value || el.dataset[s.dataset.filter] === s.value;
    });
  }

  function applyFilters() {
    toArray(list.querySelectorAll(":scope > .admin-hit")).forEach(function (el) {
      el.hidden = !matches(el);
    });
  }

  selects.forEach(function (s) { s.addEventListener("change", applyFilters); });

  // A value the page did not render an option for (a live hit's new kind, type, frontend or
  // workspace) gets one, so it can be filtered on too.
  function ensureOption(select, value, text) {
    if (!value) return;
    var known = toArray(select.options).some(function (o) { return o.value === value; });
    if (known) return;
    var option = document.createElement("option");
    option.value = value;
    option.textContent = text || value;
    select.appendChild(option);
  }

  // --- the workspace table ------------------------------------------------------------------

  function rowOf(wid) {
    var rows = toArray(document.querySelectorAll("tr[data-workspace]"));
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].dataset.workspace === wid) return rows[i];
    }
    return null;
  }

  function nameOf(wid) {
    var row = rowOf(wid);
    var link = row ? row.querySelector("a") : null;
    return link ? link.textContent : wid;
  }

  function bumpCount(wid, kind) {
    var row = rowOf(wid);
    if (!row) return; // a workspace new since the page loaded: its row comes with the next reload
    var cells = toArray(row.querySelectorAll("td.count"));
    var cell = null;
    for (var i = 0; i < cells.length; i++) {
      if (cells[i].dataset.kind === kind) cell = cells[i];
    }
    if (!cell) {
      for (var j = 0; j < cells.length; j++) {
        if (cells[j].dataset.quiet) cell = cells[j];
      }
    }
    if (cell) cell.textContent = String((parseInt(cell.textContent, 10) || 0) + 1);
  }

  // --- the event stream ---------------------------------------------------------------------

  var seen = {};
  toArray(list.querySelectorAll(":scope > .admin-hit")).forEach(function (el) {
    var hit = el.querySelector("details.hit");
    if (hit) seen[el.dataset.workspace + ":" + hit.dataset.id] = true;
  });

  function parseHtml(html) {
    var tmp = document.createElement("template");
    tmp.innerHTML = html; // the one place this script trusts markup: the server's own
    return tmp.content.firstElementChild;
  }

  function addHit(data) {
    var hit = parseHtml(data.html);
    if (!hit) return;
    var wrapper = document.createElement("div");
    wrapper.className = "admin-hit";
    hit.classList.add("new"); // hits.css's fading highlight, as on the participant page
    wrapper.dataset.kind = data.kind || "";
    wrapper.dataset.type = data.type || "";
    wrapper.dataset.frontend = data.frontend || "";
    wrapper.dataset.workspace = data.workspace;
    var head = document.createElement("div");
    head.className = "hit-workspace";
    var link = document.createElement("a");
    link.href = "/reports/" + encodeURIComponent(data.workspace) + "/hits";
    link.textContent = nameOf(data.workspace);
    head.appendChild(link);
    wrapper.appendChild(head);
    wrapper.appendChild(hit);
    var placeholder = list.querySelector(":scope > p.placeholder");
    if (placeholder) placeholder.remove();
    list.insertBefore(wrapper, list.firstChild);
    selects.forEach(function (s) {
      var key = s.dataset.filter;
      ensureOption(s, wrapper.dataset[key], key === "workspace" ? link.textContent : null);
    });
    wrapper.hidden = !matches(wrapper);
    bumpCount(data.workspace, data.kind);
  }

  var es = new EventSource("/reports/hits/events");
  var lost = false;
  es.addEventListener("hit", function (ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    var key = data.workspace + ":" + data.id;
    if (seen[key]) return;
    seen[key] = true;
    addHit(data);
  });
  es.addEventListener("error", function () { lost = true; });
  // At most one reload a minute: a stream that keeps ending at once would otherwise reload the page
  // (every hits file reread, a Coder lookup per workspace) every few seconds.
  var RELOAD_GAP_MS = 60000;
  var reloadPending = false;

  function lastReload() {
    try {
      return parseInt(sessionStorage.getItem("hits-admin-reloaded"), 10) || 0;
    } catch (e) {
      return 0;
    }
  }

  function reload() {
    try {
      sessionStorage.setItem("hits-admin-reloaded", String(Date.now()));
    } catch (e) {
      // no storage: the reload still happens, only unthrottled across pages
    }
    location.reload();
  }

  es.addEventListener("open", function () {
    // A reconnect: the stream starts at each file's end again, so what came in meanwhile is only
    // in a fresh page.
    if (!lost || reloadPending) return;
    reloadPending = true;
    setTimeout(reload, Math.max(0, lastReload() + RELOAD_GAP_MS - Date.now()));
  });
})();
