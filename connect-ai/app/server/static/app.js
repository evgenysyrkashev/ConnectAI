// Small helpers (no inline scripts allowed by the CSP).
document.addEventListener("click", function (e) {
  var t = e.target;
  if (t.dataset && (t.dataset.checkAll || t.dataset.checkNone)) {
    var name = t.dataset.checkAll || t.dataset.checkNone;
    document.querySelectorAll('input[name="' + name + '"]').forEach(function (c) { c.checked = !!t.dataset.checkAll; });
  }
});
document.addEventListener("htmx:responseError", function (e) {
  window.alert(e.detail.xhr.responseText || "Request failed");
});

// Click-to-sort for tables marked data-sortable (numeric columns sort numerically, empty cells last).
document.addEventListener("click", function (e) {
  var th = e.target.closest && e.target.closest("table[data-sortable] th");
  if (!th) return;
  var table = th.closest("table"), idx = th.cellIndex;
  var dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
  table.querySelectorAll("th").forEach(function (h) { h.removeAttribute("aria-sort"); });
  th.setAttribute("aria-sort", dir);
  var tbody = table.tBodies[0], rows = Array.prototype.slice.call(tbody.rows);
  var val = function (r) { return r.cells[idx].textContent.trim(); };
  var num = rows.every(function (r) { var v = val(r); return v === "" || v === "-" || !isNaN(parseFloat(v)) && isFinite(v); });
  var empty = function (v) { return v === "" || v === "-"; };
  rows.sort(function (a, b) {
    var x = val(a), y = val(b);
    if (empty(x) || empty(y)) return empty(x) - empty(y);
    var c = num ? parseFloat(x) - parseFloat(y) : x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" });
    return dir === "ascending" ? c : -c;
  });
  rows.forEach(function (r) { tbody.appendChild(r); });
});

// Forms marked data-autosubmit apply their filters as soon as any control changes.
document.addEventListener("change", function (e) {
  var f = e.target.closest && e.target.closest("form[data-autosubmit]");
  if (f && e.target.tagName === "SELECT") { f.submit(); }
});

// Multi-select dropdowns (.ms): click an option to toggle it; clicking outside (or Esc) closes the
// dropdown. Each option click applies immediately by submitting the form.
function msClose() {
  document.querySelectorAll(".ms-panel:not([hidden])").forEach(function (p) {
    p.hidden = true; p.parentNode.querySelector(".ms-btn").setAttribute("aria-expanded", "false");
  });
}
document.addEventListener("click", function (e) {
  var btn = e.target.closest && e.target.closest(".ms-btn");
  var opt = e.target.closest && e.target.closest(".ms-opt");
  if (opt) {
    var box = opt.closest(".ms");
    opt.setAttribute("aria-pressed", opt.getAttribute("aria-pressed") === "true" ? "false" : "true");
    box.querySelectorAll('input[type="hidden"]').forEach(function (i) { i.remove(); });
    var vals = [];
    box.querySelectorAll('.ms-opt[aria-pressed="true"]').forEach(function (o) {
      vals.push(o.dataset.value);
      var h = document.createElement("input");
      h.type = "hidden"; h.name = box.dataset.field; h.value = o.dataset.value;
      box.appendChild(h);
    });
    var joined = vals.join(", ");  // keep in sync with the template: list while it fits, else a count
    box.querySelector(".ms-btn").textContent = box.dataset.label + ": " +
      (!vals.length ? "all" : joined.length <= 28 ? joined : vals.length + " selected");
    var f = box.closest("form");
    if (f) { f.submit(); }
    return;
  }
  if (btn) {
    var panel = btn.parentNode.querySelector(".ms-panel");
    var wasOpen = !panel.hidden;
    msClose();
    if (!wasOpen) { panel.hidden = false; btn.setAttribute("aria-expanded", "true"); }
    return;
  }
  if (!(e.target.closest && e.target.closest(".ms-panel"))) { msClose(); }
});
document.addEventListener("keydown", function (e) { if (e.key === "Escape") { msClose(); } });
