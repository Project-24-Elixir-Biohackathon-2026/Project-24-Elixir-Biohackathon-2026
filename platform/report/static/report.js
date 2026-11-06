// The report editor: loads the Markdown, previews it through the service and saves it with
// If-Match so an edit made elsewhere is never overwritten. No inline script (CSP).
(function () {
  "use strict";
  var main = document.querySelector("main.editor");
  if (!main) return;
  var id = main.dataset.id;
  var canEdit = main.dataset.canEdit === "1";
  var base = "/reports/" + id;
  var source = document.getElementById("source");
  var preview = document.getElementById("preview");
  var status = document.getElementById("status");
  var saveButton = document.getElementById("save");
  var etag = null;
  var saved = "";
  var dirty = false;
  var saving = false;
  var previewTimer = null;
  var saveTimer = null;

  function say(text, kind) {
    status.textContent = text;
    status.className = kind || "";
  }

  function lastSaved(when) {
    return when ? "last saved " + when : "";
  }

  function render() {
    fetch("/reports/preview", {
      method: "POST",
      headers: { "Content-Type": "text/markdown; charset=utf-8" },
      body: source.value,
      credentials: "same-origin"
    }).then(function (r) { return r.text(); })
      .then(function (fragment) { preview.innerHTML = fragment; })
      .catch(function () { /* the preview is a convenience */ });
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(render, 500);
  }

  function scheduleSave() {
    if (!canEdit) return;
    dirty = true;
    say("unsaved changes", "dirty");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 3000);
  }

  function save() {
    if (!canEdit || saving || !dirty) return;
    clearTimeout(saveTimer);
    saving = true;
    var text = source.value;
    say("saving…");
    fetch(base + ".md", {
      method: "PUT",
      headers: { "Content-Type": "text/markdown; charset=utf-8", "If-Match": etag },
      body: text,
      credentials: "same-origin"
    }).then(function (r) {
      return r.json().then(function (body) { return { status: r.status, body: body }; });
    }).then(function (res) {
      saving = false;
      if (res.status === 200) {
        etag = res.body.etag;
        dirty = source.value !== text;
        if (dirty) { scheduleSave(); return; }
        say(lastSaved(res.body.saved), "ok");
      } else if (res.status === 412) {
        say("the report changed elsewhere; reload the page to see it (your text is kept in this box until then)", "error");
      } else if (res.status === 401) {
        say("your portal login ended; log in again in another tab, then save", "error");
      } else {
        say((res.body && res.body.error) || ("save failed (" + res.status + ")"), "error");
      }
    }).catch(function () {
      saving = false;
      say("save failed: the portal did not answer", "error");
    });
  }

  fetch(base + ".md", { credentials: "same-origin" }).then(function (r) {
    if (!r.ok) throw new Error(r.status);
    etag = r.headers.get("ETag");
    return r.text();
  }).then(function (text) {
    source.value = text;
    render();
    say(lastSaved(status.dataset.lastSaved), "ok");
  }).catch(function () {
    say("could not load the report; reload the page", "error");
  });

  source.addEventListener("input", function () {
    schedulePreview();
    scheduleSave();
  });
  if (saveButton) saveButton.addEventListener("click", save);
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
  });
  window.addEventListener("beforeunload", function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });
})();
