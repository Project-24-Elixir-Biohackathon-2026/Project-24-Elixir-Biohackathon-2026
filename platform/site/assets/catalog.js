/* Sorting and filtering for the catalog table on the Overview page.
   Added to the site by hooks.py; the table is the one inside .catalog-table. */
(function () {
  function init() {
    document.querySelectorAll(".catalog-table table").forEach(function (table) {
      var head = table.tHead.rows[0].cells;
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      var cols = Array.prototype.map.call(head, function (th) { return th.textContent.trim().toLowerCase(); });
      var statusCol = cols.indexOf("status"), entryCol = cols.indexOf("entry points");

      function values(col) {
        var seen = {};
        rows.forEach(function (r) {
          r.cells[col].querySelectorAll("code").forEach(function (c) { seen[c.textContent.trim()] = true; });
        });
        return Object.keys(seen).sort();
      }
      function select(label, opts) {
        var s = document.createElement("select");
        s.setAttribute("aria-label", label);
        s.appendChild(new Option(label + ": all", ""));
        opts.forEach(function (o) { s.appendChild(new Option(o, o)); });
        return s;
      }
      var bar = document.createElement("div");
      bar.className = "catalog-controls";
      var search = document.createElement("input");
      search.type = "search"; search.placeholder = "Filter"; search.setAttribute("aria-label", "Filter rows");
      var byStatus = statusCol >= 0 ? select("Status", values(statusCol)) : null;
      var byEntry = entryCol >= 0 ? select("Entry point", values(entryCol)) : null;
      var count = document.createElement("span");
      count.className = "catalog-count";
      [search, byStatus, byEntry, count].forEach(function (el) { if (el) bar.appendChild(el); });
      table.parentNode.insertBefore(bar, table);

      function has(cell, value) {
        return Array.prototype.some.call(cell.querySelectorAll("code"), function (c) { return c.textContent.trim() === value; });
      }
      function apply() {
        var q = search.value.trim().toLowerCase(), shown = 0;
        rows.forEach(function (r) {
          var ok = (!q || r.textContent.toLowerCase().indexOf(q) !== -1)
            && (!byStatus || !byStatus.value || has(r.cells[statusCol], byStatus.value))
            && (!byEntry || !byEntry.value || has(r.cells[entryCol], byEntry.value));
          r.style.display = ok ? "" : "none";
          if (ok) shown++;
        });
        count.textContent = shown + " of " + rows.length;
      }
      search.addEventListener("input", apply);
      [byStatus, byEntry].forEach(function (s) { if (s) s.addEventListener("change", apply); });

      var sortCol = -1, dir = 1;
      Array.prototype.forEach.call(head, function (th, i) {
        th.classList.add("sortable");
        th.setAttribute("aria-sort", "none");
        th.addEventListener("click", function () {
          dir = sortCol === i ? -dir : 1; sortCol = i;
          rows.sort(function (a, b) {
            return dir * a.cells[i].textContent.trim().localeCompare(b.cells[i].textContent.trim(), undefined, { numeric: true });
          });
          rows.forEach(function (r) { body.appendChild(r); });
          Array.prototype.forEach.call(head, function (h, j) {
            h.setAttribute("aria-sort", j === i ? (dir > 0 ? "ascending" : "descending") : "none");
          });
        });
      });
      apply();
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
