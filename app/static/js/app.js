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

    // --- copy-to-clipboard (admin reset link)
    var copyBtn = document.querySelector("[data-copy-button]");
    var copySrc = document.querySelector("[data-copy-source]");
    if (copyBtn && copySrc) {
      copySrc.addEventListener("focus", function () { copySrc.select(); });
      copyBtn.addEventListener("click", function () {
        var done = function () { copyBtn.textContent = "Copied!"; window.setTimeout(function () { copyBtn.textContent = "Copy link"; }, 2000); };
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(copySrc.value).then(done, function () { copySrc.select(); });
        } else {
          copySrc.select();
          try { document.execCommand("copy"); done(); } catch (e) { /* user can copy manually */ }
        }
      });
    }

    // --- mobile navigation (slide-in sidebar for signed-in users)
    var toggle = document.querySelector("[data-nav-toggle]");
    var nav = document.getElementById("site-nav");
    var backdrop = document.querySelector(".sidebar-backdrop");
    function setNav(open) {
      if (!nav) return;
      nav.classList.toggle("open", open);
      if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (backdrop) backdrop.hidden = !open;
    }
    if (toggle && nav) {
      toggle.addEventListener("click", function () { setNav(!nav.classList.contains("open")); });
    }
    document.querySelectorAll("[data-nav-close]").forEach(function (el) {
      el.addEventListener("click", function () { setNav(false); });
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setNav(false); });

    // --- top bar slides away when scrolling down, comes back when scrolling up
    var bar = document.querySelector(".topbar, .site-header");
    if (bar) {
      var lastY = window.scrollY, ticking = false;
      window.addEventListener("scroll", function () {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(function () {
          var y = window.scrollY;
          var menuOpen = nav && nav.classList.contains("open");
          if (y > lastY + 6 && y > 80 && !menuOpen) bar.classList.add("nav-hidden");
          else if (y < lastY - 6 || y <= 80) bar.classList.remove("nav-hidden");
          lastY = y;
          ticking = false;
        });
      }, { passive: true });
      // keep it visible while someone tabs through its links with the keyboard
      bar.addEventListener("focusin", function () { bar.classList.remove("nav-hidden"); });
    }

    // --- confirmation before destructive actions
    // Uses the site's own <dialog> instead of window.confirm(): some browsers and in-app browsers block the
    // native pop-up and silently answer "no", which made every Delete button do nothing.
    var confirmForms = document.querySelectorAll("form[data-confirm]");
    if (confirmForms.length) {
      var dlg = document.createElement("dialog");
      dlg.className = "confirm-dialog";
      dlg.setAttribute("aria-labelledby", "confirm-dialog-title");
      dlg.setAttribute("aria-describedby", "confirm-dialog-msg");
      dlg.innerHTML =
        '<h2 id="confirm-dialog-title" class="confirm-title"></h2>' +
        '<p id="confirm-dialog-msg" class="confirm-msg"></p>' +
        '<div class="confirm-actions">' +
        '<button type="button" class="btn btn-secondary" data-confirm-no>Cancel</button>' +
        '<button type="button" class="btn btn-danger-solid" data-confirm-yes>Yes, continue</button>' +
        "</div>";
      document.body.appendChild(dlg);
      var pendingForm = null;
      var close = function () { if (dlg.open) dlg.close(); pendingForm = null; };
      dlg.querySelector("[data-confirm-no]").addEventListener("click", close);
      dlg.addEventListener("cancel", function () { pendingForm = null; });   // Esc key
      dlg.querySelector("[data-confirm-yes]").addEventListener("click", function () {
        var form = pendingForm;
        close();
        if (form) { form.dataset.confirmed = "1"; form.submit(); }   // form.submit() skips this handler
      });
      confirmForms.forEach(function (form) {
        form.addEventListener("submit", function (e) {
          if (form.dataset.confirmed === "1") return;
          e.preventDefault();
          pendingForm = form;
          var msg = form.getAttribute("data-confirm");
          // "Delete this check and its photo? This can't be undone." -> title + explanation
          var cut = msg.indexOf("?");
          var title = cut > 0 ? msg.slice(0, cut + 1) : msg;
          var rest = cut > 0 ? msg.slice(cut + 1).trim() : "";
          dlg.querySelector(".confirm-title").textContent = title;   // textContent: never treated as HTML
          var body = dlg.querySelector(".confirm-msg");
          body.textContent = rest;
          body.hidden = !rest;
          var danger = /delete|deactivate/i.test(msg);
          var yes = dlg.querySelector("[data-confirm-yes]");
          yes.textContent = /delete/i.test(msg) ? "Yes, delete" : "Yes, continue";
          yes.className = danger ? "btn btn-danger-solid" : "btn btn-primary";
          if (typeof dlg.showModal === "function") {
            dlg.showModal();
            dlg.querySelector("[data-confirm-no]").focus();   // safe choice focused first
          }
          else if (window.confirm(msg)) { form.dataset.confirmed = "1"; form.submit(); }   // very old browsers
        });
      });
    }

    // --- "Back to the list" links: go back in history (keeps the search results) when we came from this site
    document.querySelectorAll("a[data-back-link]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        if (document.referrer && document.referrer.indexOf(location.origin) === 0 && history.length > 1) {
          e.preventDefault();
          history.back();
        }
      });
    });

    // --- find a dermatologist: District suggestions follow the chosen State (typing any district still works)
    document.querySelectorAll("form.doctor-search").forEach(function (form) {
      var state = form.querySelector('select[name="state"]');
      var district = form.querySelector('input[name="district"]');
      if (!state || !district) return;
      var list = form.querySelector("[data-district-list]");
      if (!list) {
        list = document.createElement("datalist");
        list.id = "district-options-" + Math.random().toString(36).slice(2, 8);
        form.appendChild(list);
      }
      district.setAttribute("list", list.id);
      district.setAttribute("autocomplete", "off");
      var data = null;
      var fill = function () {
        list.textContent = "";
        ((data && data[state.value]) || []).forEach(function (d) {
          var o = document.createElement("option"); o.value = d; list.appendChild(o);
        });
        district.placeholder = state.value ? "Choose or type your district" : "Choose your state first";
      };
      fetch(form.getAttribute("data-districts-url") || "/static/data/india_districts.json")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { data = j && j.states; fill(); })
        .catch(function () { /* no list: typing still works */ });
      state.addEventListener("change", function () { district.value = ""; fill(); });
    });

    // --- sign-up: the clinic name box only matters for doctors
    document.querySelectorAll("[data-doctor-only]").forEach(function (box) {
      var form = box.closest("form");
      var sync = function () {
        var pick = form.querySelector('input[name="account_type"]:checked');
        box.hidden = !pick || pick.value !== "doctor";
      };
      form.querySelectorAll('input[name="account_type"]').forEach(function (r) { r.addEventListener("change", sync); });
      sync();
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
    var list = form.querySelector("[data-preview-list]");
    var metaEl = form.querySelector("[data-preview-meta]");
    var errEl = form.querySelector("[data-client-error]");
    var submit = form.querySelector("[data-submit]");
    var note = form.querySelector("[data-loading-note]");
    var maxBytes = parseFloat(form.getAttribute("data-max-mb")) * 1024 * 1024;
    var minSide = parseInt(form.getAttribute("data-min-side"), 10);
    var maxFiles = parseInt(input.getAttribute("data-max-files") || "1", 10);
    var urls = [];
    var valid = false;

    function showError(msg) {
      errEl.textContent = msg;
      errEl.hidden = !msg;
      valid = !msg;
    }

    function handle(files) {
      showError("");
      preview.classList.remove("show");
      urls.forEach(function (u) { URL.revokeObjectURL(u); });
      urls = [];
      list.textContent = "";
      if (!files || !files.length) { valid = false; return; }
      if (files.length > maxFiles) return showError("Please choose up to " + maxFiles + " photos at a time.");
      var total = 0;
      for (var k = 0; k < files.length; k++) {
        var file = files[k];
        var okType = /^image\/(jpeg|png)$/.test(file.type) || /\.(jpe?g|png)$/i.test(file.name);
        if (!okType) return showError(file.name + " isn't a JPG or PNG photo.");
        if (file.size > maxBytes) return showError(file.name + " is too big. Please choose a smaller photo.");
        if (file.size === 0) return showError(file.name + " is empty. Please choose a photo.");
        total += file.size;
      }
      Array.prototype.forEach.call(files, function (file) {
        var url = URL.createObjectURL(file);
        urls.push(url);
        var img = document.createElement("img");
        img.alt = "Preview of " + file.name;
        img.onload = function () {
          if (Math.min(img.naturalWidth, img.naturalHeight) < minSide) {
            showError(file.name + " is only " + img.naturalWidth + " × " + img.naturalHeight +
              " pixels. Please use photos that are at least " + minSide + " pixels on each side.");
          }
        };
        img.onerror = function () { showError("We couldn't open " + file.name + ". Please choose a JPG or PNG photo."); };
        img.src = url;
        list.appendChild(img);
      });
      metaEl.textContent = files.length + (files.length === 1 ? " photo" : " photos") + " · " +
        (total / 1024 / 1024).toFixed(1) + " MB";
      preview.classList.add("show");
      valid = true;
    }

    input.addEventListener("change", function () { handle(input.files); });

    // --- "Take a photo": phones use their own camera app; laptops get a webcam window. The photo is added to
    // the same file list as chosen photos, so it goes through exactly the same checks.
    function addFiles(newFiles) {
      if (typeof DataTransfer === "undefined") return showError("This browser can't add camera photos. Please choose a file instead.");
      var dt = new DataTransfer();
      Array.prototype.forEach.call(input.files || [], function (f) { dt.items.add(f); });
      Array.prototype.forEach.call(newFiles, function (f) { dt.items.add(f); });
      if (dt.files.length > maxFiles) return showError("Please choose up to " + maxFiles + " photos at a time.");
      input.files = dt.files;
      handle(input.files);
    }
    var camOpen = form.querySelector("[data-camera-open]");
    var camInput = form.querySelector("[data-camera-input]");
    var dlg = form.querySelector("[data-camera-dialog]");
    if (camOpen && camInput) {
      camInput.addEventListener("change", function () { if (camInput.files.length) addFiles(camInput.files); camInput.value = ""; });
      var phone = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
      var canWebcam = dlg && typeof dlg.showModal === "function" && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
      var video = dlg && dlg.querySelector("[data-camera-video]");
      var shot = dlg && dlg.querySelector("[data-camera-shot]");
      var canvas = dlg && dlg.querySelector("[data-camera-canvas]");
      var msg = dlg && dlg.querySelector("[data-camera-msg]");
      var btn = function (name) { return dlg.querySelector("[data-camera-" + name + "]"); };
      var stream = null, blob = null, shotUrl = null;
      var stop = function () {
        if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
        if (shotUrl) { URL.revokeObjectURL(shotUrl); shotUrl = null; }
      };
      var mode = function (taken) {
        video.hidden = taken; shot.hidden = !taken;
        btn("snap").hidden = taken; btn("retake").hidden = !taken; btn("use").hidden = !taken;
      };
      var say = function (text) { msg.textContent = text; msg.hidden = !text; };

      camOpen.addEventListener("click", function () {
        if (phone || !canWebcam) { camInput.click(); return; }       // phone camera app (or file picker)
        blob = null; mode(false); say(""); video.parentNode.hidden = false; dlg.showModal();
        navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
          .then(function (s) { stream = s; video.srcObject = s; })
          .catch(function () {
            say("We couldn't open your camera. Please allow camera access in your browser, or choose a photo file instead.");
            btn("snap").hidden = true;
            video.parentNode.hidden = true;          // no empty black box when there's no camera
          });
      });
      btn("snap").addEventListener("click", function () {
        if (!stream || !video.videoWidth) return;
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        canvas.toBlob(function (b) {
          blob = b;
          if (shotUrl) URL.revokeObjectURL(shotUrl);
          shotUrl = URL.createObjectURL(b); shot.src = shotUrl; mode(true);
        }, "image/jpeg", 0.92);
      });
      btn("retake").addEventListener("click", function () { blob = null; mode(false); });
      btn("use").addEventListener("click", function () {
        if (blob) {
          var stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
          addFiles([new File([blob], "camera-" + stamp + ".jpg", { type: "image/jpeg" })]);
        }
        dlg.close();
      });
      btn("close").addEventListener("click", function () { dlg.close(); });
      dlg.addEventListener("close", stop);      // camera light goes off as soon as the window closes
    }

    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("dragover"); });
    });
    zone.addEventListener("drop", function (e) {
      if (!e.dataTransfer || !e.dataTransfer.files.length) return;
      try { input.files = e.dataTransfer.files; } catch (_) { /* older browsers */ }
      handle(e.dataTransfer.files);
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
