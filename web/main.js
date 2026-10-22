/* GAUNTLET — site behavior. Vanilla, no build step, no dependencies. */
(function () {
  "use strict";

  var root = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------- theme
     The initial theme is resolved by the inline bootstrap in <head> so
     there is no flash before first paint; here we only handle toggling. */
  var themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("gauntlet-theme", next); } catch (e) {}
    });
  }

  /* ------------------------------------------------------- nav state */
  var nav = document.getElementById("nav");
  if (nav) {
    var onScroll = function () {
      nav.classList.toggle("scrolled", window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  var navToggle = document.getElementById("navToggle");
  var navLinks = document.getElementById("navLinks");
  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      var open = navLinks.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", String(open));
    });
    navLinks.addEventListener("click", function (e) {
      if (e.target.tagName === "A") {
        navLinks.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ------------------------------------------------ reveal on scroll */
  var revealEls = document.querySelectorAll(".reveal");
  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    revealEls.forEach(function (el) { io.observe(el); });
  }

  /* --------------------------------------------- copy-to-clipboard */
  document.querySelectorAll(".copy-btn").forEach(function (btn) {
    // Captured once, before any click: re-reading innerHTML inside the
    // handler would latch "copied ✓" as the label on a rapid second click.
    var original = btn.innerHTML;
    var resetTimer = null;
    btn.addEventListener("click", function () {
      var text = btn.getAttribute("data-copy") || "";
      var done = function () {
        btn.textContent = "copied ✓";
        clearTimeout(resetTimer);
        resetTimer = setTimeout(function () { btn.innerHTML = original; }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(done);
      } else {
        done();
      }
    });
  });

  /* --------------------------------------------- terminal animation */
  var term = document.getElementById("termBody");
  if (term) {
    var LINES = [
      { t: "$ ", cls: "prompt" }, { t: "GAUNTLET_SEED=7 gauntlet run flows/smoke.yaml --workers 4\n", cls: "cmd" },
      { t: "gauntlet 0.2.0 · smoke_ip_block_a · 4 steps\n", cls: "dim" },
      { t: "[  1.36s] ", cls: "dim" }, { t: "PASS", cls: "st st-pass" }, { t: "     lint_rtl\n", cls: "" },
      { t: "[  0.97s] ", cls: "dim" }, { t: "WAIVED", cls: "st st-waived" }, { t: "   sim_unit\n", cls: "" },
      { t: "[  2.98s] ", cls: "dim" }, { t: "PASS", cls: "st st-pass" }, { t: "     sim_integration\n", cls: "" },
      { t: "[  2.33s] ", cls: "dim" }, { t: "PASS", cls: "st st-pass" }, { t: "     synth_quick\n\n", cls: "" },
      { t: "FLOW smoke_ip_block_a — ", cls: "dim" }, { t: "PASS", cls: "st st-pass" }, { t: " (7.0s)\n", cls: "dim" },
      { t: "  totals: 3 pass, 1 waived, 0 fail · 5 warnings\n", cls: "dim" }
    ];

    var cursor = document.createElement("span");
    cursor.className = "cursor";

    if (reduceMotion) {
      LINES.forEach(function (seg) { append(seg.t, seg.cls); });
      term.appendChild(cursor);
    } else {
      term.appendChild(cursor);
      var li = 0;
      var run = function () {
        if (li >= LINES.length) return;
        var seg = LINES[li++];
        // command line types char-by-char; result lines snap in as blocks.
        if (li <= 2) {
          typeText(seg.t, seg.cls, function () { setTimeout(run, 120); });
        } else {
          term.insertBefore(makeSpan(seg.t, seg.cls), cursor);
          setTimeout(run, seg.t.indexOf("\n") > -1 ? 260 : 60);
        }
      };
      setTimeout(run, 450);
    }

    function makeSpan(text, cls) {
      var s = document.createElement("span");
      if (cls) s.className = cls;
      s.textContent = text;
      return s;
    }
    function append(text, cls) { term.appendChild(makeSpan(text, cls)); }
    function typeText(text, cls, done) {
      var s = makeSpan("", cls);
      term.insertBefore(s, cursor);
      var i = 0;
      var tick = function () {
        if (i < text.length) { s.textContent += text[i++]; setTimeout(tick, 22); }
        else if (done) done();
      };
      tick();
    }
  }

  /* --------------------------------------------------- dashboard tour */
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".tour-tab"));
  var tourUrl = document.getElementById("tourUrl");
  function selectTab(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
    });
    if (tourUrl) tourUrl.textContent = tab.getAttribute("data-url") || "";
    if (focus) tab.focus();
  }
  tabs.forEach(function (tab, i) {
    tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1;
    tab.addEventListener("click", function () { selectTab(tab); });
    tab.addEventListener("keydown", function (e) {
      var next = null;
      if (e.key === "ArrowDown" || e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (e.key === "Home") next = tabs[0];
      if (e.key === "End") next = tabs[tabs.length - 1];
      if (next) { e.preventDefault(); selectTab(next, true); }
    });
  });

  /* ---------------------------------------------------- contact form */
  var form = document.getElementById("contactForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var status = document.getElementById("formStatus");
      var name = (form.elements.name.value || "").trim();
      var email = (form.elements.email.value || "").trim();
      var message = (form.elements.message.value || "").trim();
      if (!name || !email || !message) {
        if (status) { status.textContent = "Please fill in every field."; status.className = "form-status"; }
        return;
      }
      var subject = encodeURIComponent("GAUNTLET — hello from " + name);
      var body = encodeURIComponent(message + "\n\n— " + name + " (" + email + ")");
      window.location.href = "mailto:charanreddychanda27@gmail.com?subject=" + subject + "&body=" + body;
      if (status) { status.textContent = "Opening your mail client…"; status.className = "form-status ok"; }
    });
  }
})();
