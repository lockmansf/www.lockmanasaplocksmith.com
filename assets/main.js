(function () {
  "use strict";

  // Mobile menu
  var btn = document.querySelector(".menu-btn");
  var nav = document.getElementById("site-nav");
  if (btn && nav) {
    btn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && nav.classList.contains("open")) {
        nav.classList.remove("open");
        btn.setAttribute("aria-expanded", "false");
        btn.focus();
      }
    });
  }

  // Google Analytics: loads only after the visitor accepts, and never when the
  // browser sends Global Privacy Control or Do Not Track.
  var gaId = document.body.getAttribute("data-ga-id");
  var banner = document.querySelector(".cookie");
  var KEY = "lockman-consent";
  var optedOut = navigator.globalPrivacyControl === true || navigator.doNotTrack === "1";

  function readConsent() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function saveConsent(v) {
    try { localStorage.setItem(KEY, v); } catch (e) { /* storage blocked: ask again next visit */ }
  }
  function loadGA() {
    if (!gaId || window.gtag) return;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(gaId);
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", gaId, { anonymize_ip: true, allow_google_signals: false, allow_ad_personalization_signals: false });
  }
  function trackClicks() {
    document.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("a");
      if (!a || !window.gtag) return;
      if (a.href.indexOf("tel:") === 0) window.gtag("event", "phone_call_click");
      else if (a.href.indexOf("wa.me") !== -1) window.gtag("event", "whatsapp_click");
    });
  }
  function showBanner() { if (banner && gaId && !optedOut) banner.hidden = false; }

  if (gaId && !optedOut && readConsent() === "yes") loadGA();
  else if (readConsent() === null) showBanner();
  trackClicks();

  document.querySelectorAll("[data-consent]").forEach(function (b) {
    b.addEventListener("click", function () {
      var yes = b.getAttribute("data-consent") === "yes";
      saveConsent(yes ? "yes" : "no");
      banner.hidden = true;
      if (yes) loadGA();
      else if (window.gtag) location.reload();
    });
  });
  document.querySelectorAll("[data-cookie-settings]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (optedOut) { alert("Your browser's privacy signal is on, so analytics stays off."); return; }
      if (!gaId) { alert("This site does not currently use analytics cookies."); return; }
      banner.hidden = false;
    });
  });
})();
