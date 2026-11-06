// The report editor: EasyMDE (vendored) on the Markdown, the preview rendered by the
// service (so it is the same sanitized HTML readers see), saves with If-Match so an
// edit made elsewhere is never overwritten. No inline script (CSP).
(function () {
  "use strict";
  var main = document.querySelector("main.editor");
  if (!main || main.dataset.canEdit !== "1" || typeof EasyMDE === "undefined") return;
  var id = main.dataset.id;
  var base = "/reports/" + id;
  var status = document.getElementById("status");
  var saveButton = document.getElementById("save");
  var etag = null;
  var dirty = false;
  var saving = false;
  var saveTimer = null;
  var previewTimer = null;
  var previewHtml = "<p>Rendering…</p>";
  var previewTarget = null;

  function say(text, kind) {
    status.textContent = text;
    status.className = kind || "";
  }

  function lastSaved(when) {
    return when ? "Last saved " + when : "";
  }

  // The preview: EasyMDE asks for HTML on every change; the service renders it, debounced.
  function requestPreview(text) {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      fetch("/reports/preview", {
        method: "POST",
        headers: { "Content-Type": "text/markdown; charset=utf-8" },
        body: text,
        credentials: "same-origin"
      }).then(function (r) { return r.text(); })
        .then(function (fragment) {
          previewHtml = fragment;
          if (previewTarget) previewTarget.innerHTML = fragment;
        })
        .catch(function () { /* the preview is a convenience */ });
    }, 400);
  }

  var editor = new EasyMDE({
    element: document.getElementById("source"),
    autoDownloadFontAwesome: false,
    spellChecker: false,
    nativeSpellcheck: true,
    status: ["lines", "words"],
    minHeight: "60vh",
    sideBySideFullscreen: false,
    promptURLs: false,
    uploadImage: false,
    toolbar: [
      "bold", "italic", "strikethrough", "heading", "|",
      "quote", "unordered-list", "ordered-list", "table", "code", "horizontal-rule", "|",
      "link", "|",
      "preview", "side-by-side", "fullscreen"
    ],
    previewRender: function (plainText, preview) {
      previewTarget = preview;
      requestPreview(plainText);
      return previewHtml;
    }
  });

  function scheduleSave() {
    dirty = true;
    say("Unsaved changes", "dirty");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 3000);
  }

  function save() {
    if (saving || !dirty) return;
    clearTimeout(saveTimer);
    saving = true;
    var text = editor.value();
    say("Saving…");
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
        dirty = editor.value() !== text;
        if (dirty) { scheduleSave(); return; }
        say(lastSaved(res.body.saved), "ok");
      } else if (res.status === 412) {
        say("The report changed elsewhere. Reload the page to see it; your text stays in the editor until then.", "error");
      } else if (res.status === 401) {
        say("Your portal login ended. Log in again in another tab, then save.", "error");
      } else {
        say((res.body && res.body.error) || ("Save failed (" + res.status + ")"), "error");
      }
    }).catch(function () {
      saving = false;
      say("Save failed: the portal did not answer.", "error");
    });
  }

  fetch(base + ".md", { credentials: "same-origin" }).then(function (r) {
    if (!r.ok) throw new Error(r.status);
    etag = r.headers.get("ETag");
    return r.text();
  }).then(function (text) {
    editor.value(text);
    editor.codemirror.clearHistory();
    editor.codemirror.on("change", function () {
      if (editor.isSideBySideActive() || editor.isPreviewActive()) requestPreview(editor.value());
      scheduleSave();
    });
    if (window.innerWidth > 1000 && !editor.isSideBySideActive()) EasyMDE.toggleSideBySide(editor);
    say(lastSaved(status.dataset.lastSaved), "ok");
  }).catch(function () {
    say("Could not load the report; reload the page.", "error");
  });

  if (saveButton) saveButton.addEventListener("click", save);
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
  });
  window.addEventListener("beforeunload", function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });
})();
