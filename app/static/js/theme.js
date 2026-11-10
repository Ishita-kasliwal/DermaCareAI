/* Applies the visitor's saved theme before first paint (loaded synchronously in <head>).
   No saved choice -> follow the operating system (prefers-color-scheme). */
(function () {
  try {
    var t = window.localStorage.getItem("dermacareai-theme");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: fall back to the OS preference */ }
})();
