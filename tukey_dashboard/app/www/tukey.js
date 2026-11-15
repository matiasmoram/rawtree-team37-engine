// Embeds the Altair/Vega-Lite specs sent by the Shiny server and links the views:
// a time brush on V2 highlights the same hours in V1 and the same windows in V3 (linked highlighting).
window.TK = (function () {
  "use strict";
  var LOCALE = { decimal: ",", thousands: ".", grouping: [3], currency: ["", " €"] };
  var TLOCALE = {
    dateTime: "%A, %e de %B de %Y, %X", date: "%d/%m/%Y", time: "%H:%M:%S", periods: ["AM", "PM"],
    days: ["diumenge", "dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte"],
    shortDays: ["dg", "dl", "dt", "dc", "dj", "dv", "ds"],
    months: ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost", "setembre", "octubre", "novembre", "desembre"],
    shortMonths: ["gen", "feb", "març", "abr", "maig", "juny", "jul", "ag", "set", "oct", "nov", "des"]
  };
  var views = {};
  function wire() {
    var v2 = views["v2"];
    if (!v2 || v2.__tkWired) return;
    v2.__tkWired = true;
    try {
      v2.addSignalListener("brush", function (name, val) {
        var r = [0, 0];
        if (val && val.tc && val.tc.length === 2) r = [+val.tc[0], +val.tc[1]];
        ["v1", "v3"].forEach(function (id) {
          if (views[id]) { try { views[id].signal("hl", r).runAsync(); } catch (e) { /* view without hl */ } }
        });
      });
    } catch (e) { console.warn("brush link unavailable", e); }
  }
  function embed(id, spec) {
    var el = document.getElementById("c-" + id);
    if (!el) return;
    if (views[id]) { try { views[id].finalize(); } catch (e) { /* already gone */ } }
    vegaEmbed(el, spec, { actions: false, renderer: "svg", formatLocale: LOCALE, timeFormatLocale: TLOCALE })
      .then(function (res) { views[id] = res.view; wire(); })
      .catch(function (e) { el.textContent = "No s'ha pogut dibuixar aquesta vista: " + e.message; });
  }
  return { embed: embed, views: views };
})();
