(function () {
  "use strict";
  var SPECS = JSON.parse(document.getElementById("specs").textContent);
  var KEYS = ["surface", "ink", "ink2", "muted", "axis", "grid", "us", "us_light", "lost", "bench", "other", "guide",
    "band", "band2", "expected", "realised"];
  var LOCALE = { decimal: ",", thousands: ".", grouping: [3], currency: ["", " €"] };
  var TLOCALE = {
    dateTime: "%A, %e de %B de %Y, %X", date: "%d/%m/%Y", time: "%H:%M:%S", periods: ["AM", "PM"],
    days: ["diumenge", "dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte"],
    shortDays: ["dg", "dl", "dt", "dc", "dj", "dv", "ds"],
    months: ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost", "setembre", "octubre", "novembre", "desembre"],
    shortMonths: ["gen", "feb", "març", "abr", "maig", "juny", "jul", "ag", "set", "oct", "nov", "des"]
  };
  var views = {};
  var current = null;

  function tokens() {
    var cs = getComputedStyle(document.documentElement), m = {};
    KEYS.forEach(function (k) { m[k] = cs.getPropertyValue("--" + k.replace("_", "-")).trim() || "#888888"; });
    return m;
  }
  function resolve(spec, tok) {
    var s = JSON.stringify(spec).replace(/"TOK:([a-z_0-9]+)"/g, function (_, k) { return JSON.stringify(tok[k] || "#888888"); });
    return JSON.parse(s);
  }
  function finalize() {
    Object.keys(views).forEach(function (k) { try { views[k].finalize(); } catch (e) { /* view already gone */ } });
    views = {};
  }
  function wire() {
    var v2 = views.v2;
    if (!v2) return;
    try {
      v2.addSignalListener("brush", function (name, val) {
        var r = [0, 0];
        if (val && val.tc && val.tc.length === 2) r = [+val.tc[0], +val.tc[1]];
        ["v1", "v3"].forEach(function (id) {
          if (views[id]) { try { views[id].signal("hl", r).runAsync(); } catch (e) { console.warn("link", id, e); } }
        });
      });
    } catch (e) { console.warn("brush link unavailable", e); }
  }
  function render(period) {
    finalize();
    current = period;
    var tok = tokens(), set = SPECS[period] || {}, jobs = [];
    Object.keys(set).forEach(function (id) {
      var spec = set[id];
      var el = document.getElementById("c-" + period + "-" + id);
      if (!spec || !el) return;
      jobs.push(vegaEmbed(el, resolve(spec, tok), {
        actions: false, renderer: "svg", formatLocale: LOCALE, timeFormatLocale: TLOCALE,
        tooltip: { theme: document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light" }
      }).then(function (res) { views[id] = res.view; }).catch(function (e) {
        el.textContent = "No s'ha pogut dibuixar aquesta vista: " + e.message;
      }));
    });
    return Promise.all(jobs).then(wire);
  }
  function show(period) {
    document.querySelectorAll(".period").forEach(function (p) { p.hidden = p.getAttribute("data-period") !== period; });
    render(period);
  }
  document.querySelectorAll('input[name="period"]').forEach(function (r) {
    r.addEventListener("change", function () { if (r.checked) show(r.value); });
  });
  var checked = document.querySelector('input[name="period"]:checked');
  show(checked ? checked.value : "practice");
  var rerender = function () { if (current) render(current); };
  try { window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerender); } catch (e) { /* old browser */ }
  new MutationObserver(rerender).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
})();
