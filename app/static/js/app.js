/* DermaCareAI UI behaviour. Progressive enhancement: every form works without JavaScript. */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // --- light / dark theme toggle (state lives in theme.js: html.dark + saved choice)
  function currentTheme() {
    return window.dermaTheme ? window.dermaTheme.current()
      : (document.documentElement.classList.contains("dark") ? "dark" : "light");
  }
  function syncThemeButton(btn) {
    var dark = currentTheme() === "dark";
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    var label = btn.querySelector("[data-theme-label]");
    if (label) label.textContent = dark ? "Light" : "Dark";
  }

  onReady(function () {
    var themeBtn = document.querySelector("[data-theme-toggle]");
    if (themeBtn) {
      syncThemeButton(themeBtn);
      themeBtn.addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        if (window.dermaTheme) window.dermaTheme.set(next);
        syncThemeButton(themeBtn);
      });
      // theme.js fires "themechange" for OS changes too; keep the button label in sync
      document.addEventListener("themechange", function () { syncThemeButton(themeBtn); });
    }

    // --- mobile navigation
    var toggle = document.querySelector("[data-nav-toggle]");
    var nav = document.getElementById("site-nav");
    if (toggle && nav) {
      toggle.addEventListener("click", function () {
        var open = nav.classList.toggle("open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    // --- confirmation before destructive actions
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
      });
    });

    // --- loading state on submit (prevents double submission)
    document.querySelectorAll("form[data-loading-form]").forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"]');
        var note = form.querySelector("[data-loading-note]");
        window.setTimeout(function () {
          if (btn) { btn.classList.add("is-loading"); btn.setAttribute("aria-busy", "true"); }
          if (note) note.classList.add("show");
        }, 0);
      });
    });

    // --- upload: drag & drop, preview, client-side checks (server re-validates everything)
    var uform = document.querySelector("[data-upload-form]");
    if (uform) setupUpload(uform);

    // --- result page: original / heatmap toggle
    var views = document.querySelectorAll("[data-view-btn]");
    views.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.getAttribute("data-view-btn");
        document.querySelectorAll("[data-view]").forEach(function (img) {
          img.hidden = img.getAttribute("data-view") !== target;
        });
        views.forEach(function (b) { b.setAttribute("aria-pressed", b === btn ? "true" : "false"); });
      });
    });

    // --- feedback form: only ask for the clinician's category when "no" is chosen
    var fb = document.querySelector("[data-feedback-form]");
    if (fb) {
      var box = fb.querySelector("[data-suggested]");
      var sync = function () {
        var chosen = fb.querySelector('input[name="is_correct"]:checked');
        box.hidden = !(chosen && chosen.value === "no");
      };
      fb.querySelectorAll('input[name="is_correct"]').forEach(function (r) { r.addEventListener("change", sync); });
      sync();
    }

    // --- analytics date range sanity check
    var rf = document.querySelector("[data-range-form]");
    if (rf) {
      rf.addEventListener("submit", function (e) {
        var f = rf.querySelector("#from").value, t = rf.querySelector("#to").value;
        var err = rf.querySelector("[data-range-error]");
        if (f && t && f > t) {
          e.preventDefault();
          err.textContent = "The start date needs to be before the end date.";
          err.hidden = false;
        }
      });
    }
  });

  function setupUpload(form) {
    var input = form.querySelector("[data-file-input]");
    var zone = form.querySelector("[data-dropzone]");
    var preview = form.querySelector("[data-preview]");
    var img = form.querySelector("[data-preview-img]");
    var nameEl = form.querySelector("[data-preview-name]");
    var metaEl = form.querySelector("[data-preview-meta]");
    var errEl = form.querySelector("[data-client-error]");
    var submit = form.querySelector("[data-submit]");
    var note = form.querySelector("[data-loading-note]");
    var maxBytes = parseFloat(form.getAttribute("data-max-mb")) * 1024 * 1024;
    var minSide = parseInt(form.getAttribute("data-min-side"), 10);
    var objectUrl = null;
    var valid = false;

    function showError(msg) {
      errEl.textContent = msg;
      errEl.hidden = !msg;
      valid = !msg;
    }

    function handle(file) {
      showError("");
      preview.classList.remove("show");
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
      if (!file) { valid = false; return; }
      var okType = /^image\/(jpeg|png)$/.test(file.type) || /\.(jpe?g|png)$/i.test(file.name);
      if (!okType) return showError("Please choose a JPG or PNG photo.");
      if (file.size > maxBytes) return showError("This photo is too big. Please choose a smaller one.");
      if (file.size === 0) return showError("This file is empty. Please choose a photo.");
      objectUrl = URL.createObjectURL(file);
      img.onload = function () {
        var w = img.naturalWidth, h = img.naturalHeight;
        metaEl.textContent = w + " × " + h + " px · " + (file.size / 1024 / 1024).toFixed(1) + " MB";
        if (Math.min(w, h) < minSide) showError("This photo is only " + w + " × " + h + " pixels. Please use one that's at least " + minSide + " pixels on each side.");
      };
      img.onerror = function () { showError("We couldn't open this file. Please choose a JPG or PNG photo."); };
      img.src = objectUrl;
      nameEl.textContent = file.name;
      preview.classList.add("show");
      valid = true;
    }

    input.addEventListener("change", function () { handle(input.files[0]); });

    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("dragover"); });
    });
    zone.addEventListener("drop", function (e) {
      if (!e.dataTransfer || !e.dataTransfer.files.length) return;
      try { input.files = e.dataTransfer.files; } catch (_) { /* older browsers */ }
      handle(e.dataTransfer.files[0]);
    });

    form.addEventListener("submit", function (e) {
      if (!input.files || !input.files.length) { e.preventDefault(); showError("Please choose a photo to upload."); input.focus(); return; }
      if (!valid) { e.preventDefault(); input.focus(); return; }
      submit.classList.add("is-loading");
      submit.setAttribute("aria-busy", "true");
      if (note) note.classList.add("show");
    });
  }
})();
