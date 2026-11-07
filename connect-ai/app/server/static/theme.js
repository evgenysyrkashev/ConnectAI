// Light/dark theme: auto (follow OS) -> light -> dark. Loaded synchronously in <head> to avoid a flash.
(function () {
  var KEY = "theme", root = document.documentElement, modes = ["auto", "light", "dark"];
  function get() { try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; } }
  function apply(m) {
    if (m === "light" || m === "dark") root.setAttribute("data-theme", m); else root.removeAttribute("data-theme");
    var b = document.getElementById("theme-toggle");
    if (b) { b.textContent = { auto: "◐ Auto", light: "☀ Light", dark: "☾ Dark" }[m]; b.title = "Theme: " + m + " (click to change)"; }
  }
  apply(get());
  document.addEventListener("DOMContentLoaded", function () { apply(get()); });
  document.addEventListener("click", function (e) {
    if (!(e.target.closest && e.target.closest("#theme-toggle"))) return;
    var next = modes[(modes.indexOf(get()) + 1) % modes.length];
    try { localStorage.setItem(KEY, next); } catch (err) {}
    apply(next);
  });
})();
