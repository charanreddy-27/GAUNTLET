/* GAUNTLET — site behavior. Vanilla, no build step, no dependencies. */
(function () {
  "use strict";

  var root = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------- theme */
  var stored = null;
  try { stored = localStorage.getItem("gauntlet-theme"); } catch (e) {}
  if (stored) {
    root.setAttribute("data-theme", stored);
  } else if (window.matchMedia("(prefers-color-scheme: light)").matches) {
    root.setAttribute("data-theme", "light");
  }
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
    btn.addEventListener("click", function () {
      var text = btn.getAttribute("data-copy") || "";
      var done = function () {
        var original = btn.innerHTML;
        btn.textContent = "copied ✓";
        setTimeout(function () { btn.innerHTML = original; }, 1400);
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
      window.location.href = "mailto:charanreddychanda@gmail.com?subject=" + subject + "&body=" + body;
      if (status) { status.textContent = "Opening your mail client…"; status.className = "form-status ok"; }
    });
  }
})();
