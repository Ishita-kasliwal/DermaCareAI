/* Applies the colour theme before first paint (loaded synchronously in <head>).
   Tailwind uses class-based dark mode: <html class="dark">.
   Light by default; dark only when the person picks it with the theme button (saved). */
(function () {
  var KEY = "dermacareai-theme";
  var root = document.documentElement;

  function saved() {
    try {
      var t = window.localStorage.getItem(KEY);
      return t === "light" || t === "dark" ? t : null;
    } catch (e) { return null; }
  }

  function apply() {
    var t = saved() || "light";
    root.classList.toggle("dark", t === "dark");
    root.setAttribute("data-theme", t);
    return t;
  }

  window.dermaTheme = {
    current: function () { return root.classList.contains("dark") ? "dark" : "light"; },
    set: function (t) {
      try { window.localStorage.setItem(KEY, t); } catch (e) { /* storage blocked */ }
      apply();
      document.dispatchEvent(new CustomEvent("themechange", { detail: t }));
    },
  };

  apply();
})();
