// The runs browser: list, one run, one chat, drawn from the service's JSON API. The view is
// in the URL's hash (#/, #/run/<id>, #/run/<id>/chat/<frontend>/<chat>, #/workspace/<id>) so every state has a
// link. Everything is built with DOM calls; the only HTML inserted as-is is what the service
// rendered and sanitized (the report and the turns). No inline script (CSP).
(function () {
  "use strict";
  var main = document.getElementById("runs");
  if (!main) return;
  var API = main.dataset.api;
  var REPORTS = main.dataset.reports;
  var view = document.getElementById("view");
  var state = { runs: null, reports: null, filters: { q: "", participant: "", model: "", frontend: "" },
                sort: { key: "archived_at", dir: "desc" } };

  // ---- small DOM helpers
  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];       // sanitized by the service
      else if (k === "class") e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  function chips(items, cls) {
    return el("span", { class: "chips" }, (items || []).map(function (x) { return el("span", { class: "chip " + (cls || ""), text: x }); }));
  }
  function show(node) { view.replaceChildren(node); window.scrollTo(0, 0); }
  function loading() { show(el("p", { class: "muted", text: "Loading…" })); }
  function failed(what, status) {
    var msg = status === 401 ? "Your portal login ended. Log in again, then reload." : "Could not load " + what + (status ? " (" + status + ")" : "") + ".";
    show(el("div", { class: "error-box", text: msg }));
  }
  function get(path) {
    return fetch(path, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw r.status;
      return r.json();
    });
  }
  function crumbs(parts) {
    var p = el("p", { class: "crumbs" }, [el("a", { href: "#/", text: "Runs" })]);
    parts.forEach(function (x) { p.appendChild(el("span", { text: "›" })); p.appendChild(x); });
    return p;
  }
  function timeCell(s) { return el("td", {}, [el("span", { class: "when", text: s || "" })]); }

  // ---- the list
  function loadList() {
    loading();
    Promise.all([get(API + "runs"), get(API + "reports").catch(function () { return { reports: [] }; })])
      .then(function (res) { state.runs = res[0].runs || []; state.reports = res[1].reports || []; renderList(); })
      .catch(function (status) { failed("the runs", status); });
  }
  function matches(r, f) {
    if (f.participant && r.participant !== f.participant) return false;
    if (f.model && r.model !== f.model) return false;
    if (f.frontend && (r.frontends || []).indexOf(f.frontend) < 0) return false;
    if (f.q) {
      var hay = [r.participant, r.workspace, r.instance, r.model, r.flavor, (r.workflows || []).join(" ")].join(" ").toLowerCase();
      if (hay.indexOf(f.q.toLowerCase()) < 0) return false;
    }
    return true;
  }
  function chatCount(r) { var c = r.chats || {}; return (c.openwebui || 0) + (c.agui || 0); }
  function sortRuns(rows) {
    var k = state.sort.key, d = state.sort.dir === "asc" ? 1 : -1;
    return rows.slice().sort(function (a, b) {
      var x = k === "chats" ? chatCount(a) : (a[k] || ""), y = k === "chats" ? chatCount(b) : (b[k] || "");
      return (x < y ? -1 : x > y ? 1 : 0) * d;
    });
  }
  function uniq(key) {
    var seen = {};
    state.runs.forEach(function (r) { (key === "frontends" ? r.frontends || [] : [r[key]]).forEach(function (v) { if (v) seen[v] = 1; }); });
    return Object.keys(seen).sort();
  }
  function select(key, label, values) {
    var s = el("select", { "aria-label": label }, [el("option", { value: "", text: label })].concat(values.map(function (v) {
      return el("option", { value: v, text: v });
    })));
    s.value = values.indexOf(state.filters[key]) >= 0 ? state.filters[key] : "";
    s.addEventListener("change", function () { state.filters[key] = s.value; renderList(); });
    return s;
  }
  function renderList() {
    var runs = state.runs, reports = state.reports;
    var rows = sortRuns(runs.filter(function (r) { return matches(r, state.filters); }));
    var participants = uniq("participant");
    var totalChats = runs.reduce(function (n, r) { return n + chatCount(r); }, 0);
    var filled = runs.filter(function (r) { return r.report && r.report.filled; }).length;

    var tiles = el("div", { class: "tiles" }, [
      tile(runs.length, "archived runs"), tile(participants.length, "participants"),
      tile(totalChats, "chats"), tile(filled, "reports filled in"), tile(reports.length, "live reports")
    ]);
    var q = el("input", { type: "search", placeholder: "Search participant, workspace, model…", value: state.filters.q, "aria-label": "Search" });
    q.addEventListener("input", function () { state.filters.q = q.value; renderTable(); });
    var filters = el("div", { class: "filters" }, [
      q, select("participant", "All participants", participants), select("model", "All models", uniq("model")),
      select("frontend", "All frontends", uniq("frontends")), el("span", { class: "count", id: "count" })
    ]);
    var tableCard = el("section", { class: "card table-card", id: "runs-table" });
    var live = el("section", { class: "card table-card" }, [reportsTable(reports)]);
    show(el("div", {}, [tiles, filters, tableCard, el("h2", { text: "Live reports" }),
      el("p", { class: "muted", text: "Reports of the workspaces that exist now, written by their owners while testing. A stopped workspace's report is also in its run above." }), live]));
    renderTable();

    function renderTable() {
      rows = sortRuns(runs.filter(function (r) { return matches(r, state.filters); }));
      document.getElementById("count").textContent = rows.length + " of " + runs.length + " runs";
      document.getElementById("runs-table").replaceChildren(runsTable(rows));
    }
  }
  function tile(n, k) { return el("div", { class: "tile" }, [el("div", { class: "n", text: String(n) }), el("div", { class: "k", text: k })]); }
  function th(key, label, numeric) {
    var h = el("th", { class: "sortable", text: label, scope: "col" });
    if (state.sort.key === key) h.setAttribute("aria-sort", state.sort.dir === "asc" ? "ascending" : "descending");
    h.addEventListener("click", function () {
      if (state.sort.key === key) state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
      else { state.sort.key = key; state.sort.dir = numeric || key === "archived_at" ? "desc" : "asc"; }
      renderList();
    });
    return h;
  }
  function runsTable(rows) {
    if (!rows.length) return el("p", { class: "muted", text: "No run matches." });
    var head = el("tr", {}, [th("archived_at", "Archived"), th("participant", "Participant"), th("workspace", "Workspace"),
      th("model", "Model"), el("th", { text: "Frontends", scope: "col" }), th("chats", "Chats", true), el("th", { text: "Report", scope: "col" })]);
    var body = el("tbody", {}, rows.map(function (r) {
      var rep = !r.report ? el("span", { class: "chip", text: "none" })
        : r.report.filled ? el("span", { class: "chip ok", text: "filled in" })
        : r.report.filled === false ? el("span", { class: "chip warn", text: "empty" }) : el("span", { class: "chip", text: "present" });
      return el("tr", {}, [
        el("td", {}, [el("a", { href: "#/run/" + encodeURIComponent(r.id), text: r.archived_at || r.id })]),
        el("td", { text: r.participant }), el("td", {}, [el("a", { href: "#/run/" + encodeURIComponent(r.id), text: r.workspace || r.instance })]),
        el("td", { text: r.model }), el("td", {}, [chips(r.frontends)]),
        el("td", { class: "num", text: String(chatCount(r)) }), el("td", {}, [rep])
      ]);
    }));
    return el("table", {}, [el("thead", {}, [head]), body]);
  }
  function reportsTable(reports) {
    if (!reports.length) return el("p", { class: "muted", text: "No live report." });
    var head = el("tr", {}, ["Workspace", "Owner", "Instance", "Created", "Last saved"].map(function (t) { return el("th", { text: t, scope: "col" }); }));
    var body = el("tbody", {}, reports.map(function (r) {
      return el("tr", {}, [
        el("td", {}, [el("a", { href: REPORTS + r.workspace_id, text: r.workspace || r.workspace_id })]),
        el("td", { text: r.owner || "" }), el("td", {}, [el("code", { text: r.instance || "" })]),
        timeCell(r.created), timeCell(r.last_saved)
      ]);
    }));
    return el("table", {}, [el("thead", {}, [head]), body]);
  }

  // ---- one run
  function loadRun(id) {
    loading();
    get(API + "runs/" + encodeURIComponent(id)).then(renderRun).catch(function (status) { failed("the run", status); });
  }
  function fact(k, v) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) return null;
    return el("div", { class: "fact" }, [el("span", { class: "k", text: k }), el("span", { class: "v", text: Array.isArray(v) ? v.join(", ") : String(v) })]);
  }
  function renderRun(r) {
    var base = API + "runs/" + encodeURIComponent(r.id) + "/";
    var facts = el("div", { class: "facts" }, [
      fact("Participant", r.participant), fact("Workspace", r.workspace), fact("Instance", r.instance),
      fact("Archived", r.archived_at), fact("Model", r.model), fact("Flavor", r.flavor), fact("Seed", r.seed),
      fact("Frontends", r.frontends), fact("Workflows", r.workflows), fact("Samples", r.samples), fact("Tiers", r.tiers)
    ]);
    var raw = el("div", { class: "raw-links" }, [
      el("a", { href: base, text: "JSON" }),
      r.report ? el("a", { href: base + "report.md", text: "Report (Markdown)" }) : null,
      r.files && r.files.agent_runs ? el("a", { href: base + "agui/agent-runs.jsonl", text: "Agent run log (JSONL)" }) : null,
      r.report && r.report.workspace_id ? el("a", { href: REPORTS + r.report.workspace_id, text: "Live report page" }) : null,
      r.report && r.report.workspace_id ? el("a", { href: "#/workspace/" + r.report.workspace_id, text: "All runs of this workspace" }) : null
    ]);
    var head = el("header", { class: "card run-head" }, [el("h1", { text: (r.workspace || r.instance) + " by " + (r.participant || "?") }), facts, raw]);

    var report = el("article", { class: "card reading run-report" }, [el("h2", { text: "Report" })]);
    if (!r.report) report.appendChild(el("p", { class: "empty", text: "No report was archived with this run." }));
    else {
      if (r.report.filled === false) report.appendChild(el("p", { class: "empty", text: "The report was never filled in; this is the template." }));
      report.appendChild(el("div", { html: r.report.html }));
    }
    var chats = el("section", { class: "card list-card" }, [el("h2", { text: "Chats" })]);
    var list = r.chat_list || [];
    if (!list.length) chats.appendChild(el("p", { class: "muted", text: "No chat was exported for this run." }));
    ["openwebui", "agui"].forEach(function (f) {
      var mine = list.filter(function (c) { return c.frontend === f; });
      if (!mine.length) return;
      chats.appendChild(el("h2", { text: f === "agui" ? "AG-UI chat" : "Open WebUI" }));
      var scored = mine.some(function (c) { return c.threat; });
      var body = el("tbody", {}, mine.map(function (c) {
        return el("tr", {}, [
          el("td", {}, [el("a", { href: "#/run/" + encodeURIComponent(r.id) + "/chat/" + f + "/" + encodeURIComponent(c.id), text: c.title })]),
          timeCell(c.created), el("td", { class: "num", text: String(c.messages) }),
          scored ? el("td", {}, [c.threat ? threatChip(c.threat, "Highest threat score among the user turns") : null]) : null,
          el("td", {}, [chips(c.tags)])
        ]);
      }));
      chats.appendChild(el("table", {}, [el("thead", {}, [el("tr", {}, ["Chat", "Created", "Messages"].concat(scored ? ["Threat"] : [], ["Tags"]).map(function (t) { return el("th", { text: t, scope: "col" }); }))]), body]));
    });
    if (r.files && r.files.journals && r.files.journals.length) {
      chats.appendChild(el("h2", { text: "AG-UI session journals (raw)" }));
      chats.appendChild(el("p", { class: "muted" }, r.files.journals.reduce(function (acc, j, i) {
        if (i) acc.push(", ");
        acc.push(el("a", { href: base + "agui/journals/" + j + ".jsonl", text: j.slice(0, 8) }));
        return acc;
      }, [])));
    }
    show(el("div", {}, [crumbs([el("span", { text: r.workspace || r.id })]), head, el("div", { class: "two" }, [report, chats])]));
    document.title = "Run " + (r.workspace || r.id);
  }

  // ---- the threat score of a user turn (the service scores it; absent when it has no embeddings endpoint)
  // In a table: the dot and the number only; the level is in the title.
  function threatChip(t, title) {
    return el("span", { class: "threat compact " + t.level, title: title + ": " + t.score + " (" + t.level + ")" },
      [el("span", { class: "dot" }), el("strong", { text: String(t.score) })]);
  }
  function threatToggle(t, details) {
    var b = el("button", { type: "button", class: "threat " + t.level, "aria-expanded": "false", title: "Show the score per category" },
      [el("span", { class: "dot" }), "Threat score ", el("strong", { text: String(t.score) }), " ", el("span", { class: "level", text: t.level })]);
    b.addEventListener("click", function () {
      details.hidden = !details.hidden;
      b.setAttribute("aria-expanded", details.hidden ? "false" : "true");
    });
    return b;
  }
  function weakness(c) {
    if (c.examples < 5) return "only " + c.examples + (c.examples === 1 ? " example" : " examples");
    if (c.auc !== null && c.auc < 0.8) return "weak detector";
    return null;
  }
  function threatDetails(t, model) {
    var rows = (t.categories || []).map(function (c) {
      var bar = el("span", { class: "meter" }, [el("span", {})]);
      bar.firstChild.style.width = c.score + "%";
      var weak = weakness(c);
      return el("li", { class: c.level }, [el("span", { class: "name" }, [c.label, weak ? el("small", { text: weak }) : null]), bar,
        el("span", { class: "n", text: String(c.score) })]);
    });
    var d = el("div", { class: "threat-details" }, [
      el("p", { text: "How much this message resembles known adversarial prompts, per detector. 0 to 100: from 50, only 5% of benign prompts score higher; from 75, 1%. Violations that read like ordinary work are often missed." }),
      el("ul", {}, rows),
      model ? el("p", { class: "muted", text: "Model of " + model.trained + ", " + model.embedding_model + " embeddings." }) : null
    ]);
    d.hidden = true;
    return d;
  }

  // ---- one chat
  function loadChat(id, frontend, chat) {
    loading();
    get(API + "runs/" + encodeURIComponent(id) + "/chats/" + frontend + "/" + encodeURIComponent(chat))
      .then(renderChat).catch(function (status) { failed("the chat", status); });
  }
  function renderChat(c) {
    var facts = el("div", { class: "facts" }, Object.keys(c.facts || {}).map(function (k) { return fact(k, c.facts[k]); }));
    var head = el("header", { class: "card chat-head" }, [
      el("h1", { text: c.title }), facts,
      el("div", { class: "raw-links" }, [el("span", { class: "chip " + (c.frontend === "agui" ? "agui" : ""), text: c.frontend === "agui" ? "AG-UI" : "Open WebUI" }),
        el("a", { href: c.links.markdown, text: "Markdown" }), el("a", { href: c.links.json, text: "JSON" })])
    ]);
    var turns = el("div", { class: "turns" }, (c.turns || []).map(function (t) {
      var meta = el("div", { class: "meta" }, [el("span", { class: "role", text: t.label || t.role }),
        t.model ? el("span", { text: t.model }) : null, t.at ? el("span", { text: t.at }) : null]);
      var details = t.threat ? threatDetails(t.threat, c.threat_model) : null;
      if (details) meta.appendChild(threatToggle(t.threat, details));
      return el("article", { class: "turn " + t.role }, [meta, details, el("div", { class: "body", html: t.html })]);
    }));
    if (!(c.turns || []).length) turns.appendChild(el("p", { class: "muted", text: "This chat has no messages." }));
    show(el("div", {}, [crumbs([el("a", { href: "#/run/" + encodeURIComponent(c.run), text: c.run }), el("span", { text: c.title })]), head, turns]));
    document.title = c.title;
  }

  // ---- one workspace: its runs, each with its chats (the "Chats" button of a Coder workspace lands here)
  function loadWorkspace(wid) {
    loading();
    get(API + "workspaces/" + encodeURIComponent(wid)).then(renderWorkspace).catch(function (status) { failed("the workspace", status); });
  }
  function chatsTable(r) {
    var list = r.chat_list || [];
    if (!list.length) return el("p", { class: "muted", text: "No chat was exported for this run." });
    var body = el("tbody", {}, list.map(function (c) {
      return el("tr", {}, [
        el("td", {}, [el("a", { href: "#/run/" + encodeURIComponent(r.id) + "/chat/" + c.frontend + "/" + encodeURIComponent(c.id), text: c.title })]),
        el("td", {}, [el("span", { class: "chip " + (c.frontend === "agui" ? "agui" : ""), text: c.frontend === "agui" ? "AG-UI" : "Open WebUI" })]),
        timeCell(c.created), el("td", { class: "num", text: String(c.messages) })
      ]);
    }));
    return el("table", {}, [el("thead", {}, [el("tr", {}, ["Chat", "Frontend", "Created", "Messages"].map(function (t) { return el("th", { text: t, scope: "col" }); }))]), body]);
  }
  function renderWorkspace(w) {
    var live = w.live_report;
    var first = w.runs[0];
    var name = (live && live.workspace) || (first && first.workspace) || w.workspace_id;
    var owner = (live && live.owner) || (first && first.participant) || "";
    var head = el("header", { class: "card run-head" }, [
      el("h1", { text: "Chats of " + name + (owner ? " by " + owner : "") }),
      el("div", { class: "facts" }, [fact("Workspace", name), fact("Owner", owner), fact("Instance", live ? live.instance : first ? first.instance : ""),
        fact("Archived runs", w.runs.length), fact("Live report", live ? (live.last_saved ? "saved " + live.last_saved : "present") : "none")]),
      el("div", { class: "raw-links" }, [
        live ? el("a", { href: REPORTS + w.workspace_id, text: "Report" }) : null,
        el("a", { href: API + "workspaces/" + encodeURIComponent(w.workspace_id), text: "JSON" })
      ])
    ]);
    var parts = [crumbs([el("span", { text: name })]), head];
    if (!w.runs.length) {
      parts.push(el("section", { class: "card list-card" }, [el("p", { class: "muted", text: "No archived run yet. A workspace's chats are archived when it is stopped; until then they live in the workspace." })]));
    }
    w.runs.forEach(function (r) {
      parts.push(el("section", { class: "card list-card" }, [
        el("h2", {}, [el("a", { href: "#/run/" + encodeURIComponent(r.id), text: "Run archived " + (r.archived_at || r.id) }),
          r.report && r.report.filled ? el("span", { class: "chip ok", text: " report filled in" }) : null]),
        chatsTable(r)
      ]));
    });
    show(el("div", {}, parts));
    document.title = "Chats of " + name;
  }

  // ---- routing on the hash
  function route() {
    var h = location.hash.replace(/^#\/?/, "");
    var parts = h ? h.split("/").map(decodeURIComponent) : [];
    if (parts.length >= 5 && parts[0] === "run" && parts[2] === "chat") return loadChat(parts[1], parts[3], parts[4]);
    if (parts.length >= 2 && parts[0] === "run") return loadRun(parts[1]);
    if (parts.length >= 2 && parts[0] === "workspace") return loadWorkspace(parts[1]);
    document.title = "Runs";
    if (state.runs) renderList(); else loadList();
  }
  window.addEventListener("hashchange", route);
  route();
})();
