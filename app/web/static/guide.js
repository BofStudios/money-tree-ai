(function () {
    var saved = null;
    try { saved = localStorage.getItem("mt_guide_lang"); } catch (e) { /* none */ }
    var lang = saved || ((navigator.language || "").toLowerCase().indexOf("tr") === 0 ? "tr" : "en");
    function set(l) {
      document.body.className = l;
      document.documentElement.lang = l;
      document.querySelectorAll("[data-set]").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-set") === l); });
      try { localStorage.setItem("mt_guide_lang", l); } catch (e) { /* none */ }
    }
    document.querySelectorAll("[data-set]").forEach(function (b) {
      b.addEventListener("click", function () { set(b.getAttribute("data-set")); });
    });
    set(lang);
  })();
