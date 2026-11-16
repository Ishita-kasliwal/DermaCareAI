/* Charts for the overview and admin analytics pages. All data comes from the JSON API, which
   aggregates real database records; nothing is generated client-side.
   Colours are read from the CSS design tokens, so charts follow the light/dark theme. */
(function () {
  "use strict";

  var charts = [];
  var renderers = [];

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function palette() {
    return {
      primary: token("--primary"), primarySoft: token("--primary-soft"), accent: token("--accent"),
      ink: token("--ink-2"), line: token("--line"), surface: token("--surface"),
      risk: { high: token("--high"), medium: token("--medium"), low: token("--low") },
      grey: token("--muted")
    };
  }

  function axes(C, horizontal) {
    var value = { beginAtZero: true, grid: { color: C.line }, ticks: { color: C.ink, precision: 0 }, border: { color: C.line } };
    var cat = { grid: { display: false }, ticks: { color: C.ink }, border: { color: C.line } };
    return horizontal ? { x: value, y: cat } : { x: cat, y: value };
  }

  function base(C, extra) {
    var o = {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { intersect: false } },
      scales: axes(C, false)
    };
    return Object.assign(o, extra || {});
  }

  function make(canvas, config) { var c = new Chart(canvas, config); charts.push(c); return c; }

  function renderAll() {
    charts.forEach(function (c) { c.destroy(); });
    charts = [];
    var C = palette();
    Chart.defaults.color = C.ink;
    Chart.defaults.borderColor = C.line;
    renderers.forEach(function (fn) { fn(C); });
  }

  function getJSON(url) {
    return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }

  function el(tag, text) { var e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; }

  function table(headers, rows) {
    var t = el("table"), thead = el("thead"), tr = el("tr");
    headers.forEach(function (h) { var th = el("th", h); th.scope = "col"; tr.appendChild(th); });
    thead.appendChild(tr); t.appendChild(thead);
    var tb = el("tbody");
    rows.forEach(function (r) { var row = el("tr"); r.forEach(function (c) { row.appendChild(el("td", String(c))); }); tb.appendChild(row); });
    t.appendChild(tb);
    var wrap = el("div"); wrap.className = "table-wrap"; wrap.appendChild(t);
    return wrap;
  }

  // Everyday name from the API ("Common mole"), never the medical term
  function simpleName(r) { return r.simple_name || r.name; }

  function pct(x) { return x === null || x === undefined ? "—" : Math.round(x * 100) + "%"; }

  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  ready(function () {
    if (typeof window.Chart === "undefined") return;
    document.addEventListener("themechange", function () { if (renderers.length) renderAll(); });

    // ---- user overview: results by category
    var uc = document.querySelector('[data-chart="user-classes"]');
    if (uc) {
      var status = uc.parentElement.querySelector("[data-chart-status]");
      getJSON(uc.getAttribute("data-src")).then(function (d) {
        var rows = d.by_class.filter(function (r) { return r.count > 0; });  // only categories you've had
        renderers.push(function (C) {
          make(uc.querySelector("canvas"), {
            type: "bar",
            data: { labels: rows.map(function (r) { return simpleName(r); }),
                    datasets: [{ data: rows.map(function (r) { return r.count; }),
                                 backgroundColor: rows.map(function (r) { return C.risk[r.risk_level] || C.grey; }),
                                 borderRadius: 3, maxBarThickness: 22 }] },
            options: base(C, { indexAxis: "y", scales: axes(C, true) })
          });
        });
        renderAll();
      }).catch(function () { status.hidden = false; status.textContent = "The chart couldn't be loaded. Refresh the page to try again."; });
    }

    // ---- admin analytics
    var root = document.querySelector("[data-analytics]");
    if (!root) return;
    var st = root.querySelector("[data-chart-status]");
    getJSON(root.getAttribute("data-src")).then(function (d) {
      st.hidden = d.total > 0;
      if (d.total === 0) { st.textContent = "No analyses were recorded between " + d.range.from + " and " + d.range.to + "."; return; }
      root.querySelector("[data-figures]").hidden = false;
      root.querySelector("[data-charts]").hidden = false;
      root.querySelector('[data-fig="total"]').textContent = d.total;
      root.querySelector('[data-fig="inconclusive"]').textContent = pct(d.status.inconclusive / d.total);
      root.querySelector('[data-fig="quality"]').textContent = pct(d.quality_issue_rate);

      function canvas(name) { return root.querySelector('[data-chart="' + name + '"]'); }

      renderers.push(function (C) {
        make(canvas("daily"), {
          type: "line",
          data: { labels: d.daily.map(function (r) { return r.date; }),
                  datasets: [{ data: d.daily.map(function (r) { return r.count; }), borderColor: C.primary,
                               backgroundColor: C.primarySoft, fill: true, pointRadius: 0, tension: 0.2 }] },
          options: base(C, { scales: (function () { var a = axes(C, false); a.x.ticks.maxTicksLimit = 10; return a; })() })
        });
        make(canvas("classes"), {
          type: "bar",
          data: { labels: d.by_class.map(function (r) { return simpleName(r); }),
                  datasets: [{ data: d.by_class.map(function (r) { return r.count; }),
                               backgroundColor: d.by_class.map(function (r) { return C.risk[r.risk_level] || C.grey; }), borderRadius: 3 }] },
          options: base(C, { indexAxis: "y", scales: axes(C, true) })
        });
        make(canvas("status"), {
          type: "doughnut",
          data: { labels: ["Confident", "Inconclusive"],
                  datasets: [{ data: [d.status.confident, d.status.inconclusive], backgroundColor: [C.primary, C.grey],
                               borderColor: C.surface, borderWidth: 2 }] },
          options: { responsive: true, maintainAspectRatio: false, animation: false, cutout: "62%",
                     plugins: { legend: { position: "bottom", labels: { color: C.ink } } } }
        });
        make(canvas("confidence"), {
          type: "bar",
          data: { labels: d.confidence_histogram.map(function (r) { return r.bin; }),
                  datasets: [{ data: d.confidence_histogram.map(function (r) { return r.count; }), backgroundColor: C.accent, borderRadius: 2 }] },
          options: base(C)
        });
        make(canvas("models"), {
          type: "bar",
          data: { labels: d.by_model.map(function (r) { return r.version; }),
                  datasets: [{ data: d.by_model.map(function (r) { return r.count; }), backgroundColor: C.primary, borderRadius: 3, maxBarThickness: 40 }] },
          options: base(C)
        });
      });
      renderAll();

      // feedback table
      var fbBox = root.querySelector("[data-feedback-table]");
      var codes = Object.keys(d.feedback_by_class);
      if (!codes.length) fbBox.appendChild(el("p", "No clinician feedback has been submitted for this period."));
      else fbBox.appendChild(table(["Top category", "Clinician agreed", "Clinician disagreed", "Agreement"],
        codes.map(function (c) { var f = d.feedback_by_class[c], n = f.agree + f.disagree; return [c, f.agree, f.disagree, pct(f.agree / n)]; })));

      // accessible data tables
      var raw = root.querySelector("[data-raw-tables]");
      raw.appendChild(el("h3", "By category"));
      raw.appendChild(table(["Category", "Analyses"], d.by_class.map(function (r) { return [simpleName(r), r.count]; })));
      raw.appendChild(el("h3", "Top-score distribution"));
      raw.appendChild(table(["Score range", "Analyses"], d.confidence_histogram.map(function (r) { return [r.bin, r.count]; })));
      raw.appendChild(el("h3", "By model version"));
      raw.appendChild(table(["Model version", "Analyses"], d.by_model.map(function (r) { return [r.version, r.count]; })));
      raw.appendChild(el("h3", "Per day (days with analyses)"));
      raw.appendChild(table(["Date", "Analyses"], d.daily.filter(function (r) { return r.count; }).map(function (r) { return [r.date, r.count]; })));
    }).catch(function () { st.hidden = false; st.textContent = "Analytics couldn't be loaded. Refresh the page to try again."; });
  });
})();
