/* GAUNTLET playground — the real scheduler's rules, replayed in the browser.
 *
 * Same semantics as gauntlet/scheduler.py + parsing/parser.py + diff.py:
 *   - a step starts only when every dependency is PASS or WAIVED
 *   - FAIL / TIMEOUT / SKIPPED dependencies cascade SKIPPED downstream
 *   - after the first failure nothing new is submitted; in-flight steps finish
 *   - an unwaived ERROR fails a step even if the tool exited 0;
 *     a step whose every ERROR is waived is WAIVED, never silently PASS
 *   - the diff buckets NEW FAILURES / FIXED / STILL FAILING, and SKIPPED is
 *     not evidence against a step
 * Vanilla JS, no dependencies.
 */
(function () {
  "use strict";

  var app = document.getElementById("pgApp");
  if (!app) return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var SVGNS = "http://www.w3.org/2000/svg";
  var PASSING = { PASS: 1, WAIVED: 1 };
  var BLOCKING = { FAIL: 1, TIMEOUT: 1, SKIPPED: 1 };
  var FAILING = { FAIL: 1, TIMEOUT: 1 };

  var STEPS = [
    { id: "lint_rtl", deps: [], dur: 1.22, tool: "mock_lint · rulepack lint" },
    { id: "sim_unit", deps: ["lint_rtl"], dur: 0.82, tool: "mock_sim --suite unit" },
    { id: "sim_integration", deps: ["lint_rtl"], dur: 2.83, tool: "mock_sim --suite integration" },
    { id: "synth_quick", deps: ["sim_unit", "sim_integration"], dur: 2.23, tool: "mock_synth --effort quick" }
  ];
  var BY_ID = {};
  STEPS.forEach(function (s) { BY_ID[s.id] = s; });

  var state = { faults: { flake: false, hang: false, lint: false }, waiver: true, running: false };
  var history = [];
  var timers = [];

  /* ------------------------------------------------------------ outcomes */

  // What each tool's log would contain under the current faults, and what the
  // parser + waivers make of it. Mirrors the mock tools in tools/mock/.
  function outcome(id) {
    var errors = [];
    var note = "";
    if (id === "lint_rtl") {
      if (state.faults.lint) errors.push({ rule: "LINT-201", msg: "inferred latch on 'state_q' (fsm.v:57)", waived: false });
      note = "4 warnings";
    } else if (id === "sim_unit") {
      errors.push({ rule: "SIM-ERR-007", msg: "fifo overflow in u_fifo_rx", waived: state.waiver });
      if (state.faults.flake) errors.push({ rule: "SIM-ERR-007", msg: "fifo overflow in u_fifo_tx", waived: false });
    } else if (id === "sim_integration") {
      if (state.faults.hang) return { status: "TIMEOUT", note: "timed out at 60s · process group killed", errors: [] };
      note = "1 warning";
    } else {
      note = "clean";
    }
    var unwaived = errors.filter(function (e) { return !e.waived; });
    if (unwaived.length) {
      return { status: "FAIL", note: "[" + unwaived[0].rule + "] " + unwaived[0].msg, errors: errors };
    }
    if (errors.length) {
      return { status: "WAIVED", note: errors.length + " error waived · IPREG-1301", errors: errors };
    }
    return { status: "PASS", note: note, errors: [] };
  }

  /* --------------------------------------------------------- the schedule */

  // Plays the ready-set scheduler forward in simulated time. `durOf` decides
  // how long each step takes, so the same rules produce both the real
  // timings (for the log) and a watchable playback.
  function schedule(durOf) {
    var pending = STEPS.map(function (s) { return s.id; });
    var status = {};
    var events = [];
    var running = [];
    var now = 0;
    var stop = false;

    function flush() {
      var progressed = true;
      while (progressed) {
        progressed = false;
        for (var i = 0; i < pending.length; i++) {
          var id = pending[i];
          var deps = BY_ID[id].deps.map(function (d) { return status[d]; });
          if (deps.some(function (d) { return BLOCKING[d]; })) {
            status[id] = "SKIPPED";
            events.push({ id: id, status: "SKIPPED", start: now, end: now, note: "upstream failure" });
            pending.splice(i, 1); progressed = true; break;
          }
          if (!stop && deps.every(function (d) { return PASSING[d]; })) {
            running.push({ id: id, start: now, end: now + durOf(id) });
            pending.splice(i, 1); progressed = true; break;
          }
        }
      }
    }

    flush();
    while (running.length) {
      running.sort(function (a, b) { return a.end - b.end; });
      var done = running.shift();
      now = done.end;
      var out = outcome(done.id);
      status[done.id] = out.status;
      events.push({ id: done.id, status: out.status, start: done.start, end: done.end, note: out.note });
      if (!PASSING[out.status]) stop = true;
      flush();
    }
    pending.forEach(function (id) {
      status[id] = "SKIPPED";
      events.push({ id: id, status: "SKIPPED", start: now, end: now, note: "upstream failure" });
    });
    return { events: events, status: status, total: now };
  }

  function simDuration(id) {
    if (id === "sim_integration" && state.faults.hang) return 60;
    return BY_ID[id].dur;
  }
  function playDuration(id) {
    if (reduceMotion) return 0.05;
    if (id === "sim_integration" && state.faults.hang) return 3.4;
    return BY_ID[id].dur * 0.8;
  }

  /* ------------------------------------------------------------- the DAG */

  var dag = document.getElementById("pgDag");
  var layout = null;
  var nodes = {};
  var edges = [];

  function layoutFor(width) {
    if (width < 560) {
      return {
        vb: "0 0 400 336", w: 186, h: 66, dir: "TB",
        pos: { lint_rtl: [107, 6], sim_unit: [4, 135], sim_integration: [210, 135], synth_quick: [107, 264] }
      };
    }
    return {
      vb: "0 0 700 186", w: 196, h: 70, dir: "LR",
      pos: { lint_rtl: [4, 58], sim_unit: [252, 6], sim_integration: [252, 110], synth_quick: [500, 58] }
    };
  }

  function el(name, attrs, parent) {
    var node = document.createElementNS(SVGNS, name);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(node);
    return node;
  }

  function drawDag() {
    var width = dag.getBoundingClientRect().width || 700;
    var next = layoutFor(width);
    if (layout && layout.dir === next.dir) return;
    layout = next;
    var keep = {}, keepText = {};
    Object.keys(nodes).forEach(function (id) {
      keep[id] = nodes[id].group.getAttribute("class");
      keepText[id] = nodes[id].sub.textContent;
    });
    dag.innerHTML = "";
    var svg = el("svg", { viewBox: layout.vb, role: "img", "aria-label": "smoke flow: lint_rtl gates sim_unit and sim_integration, which both gate synth_quick" }, dag);
    var gEdges = el("g", {}, svg);
    edges = [];
    STEPS.forEach(function (s) {
      s.deps.forEach(function (d) {
        var a = layout.pos[d], b = layout.pos[s.id], w = layout.w, h = layout.h, path;
        if (layout.dir === "LR") {
          var x1 = a[0] + w, y1 = a[1] + h / 2, x2 = b[0], y2 = b[1] + h / 2, mx = (x1 + x2) / 2;
          path = "M" + x1 + " " + y1 + " C" + mx + " " + y1 + " " + mx + " " + y2 + " " + x2 + " " + y2;
        } else {
          var X1 = a[0] + w / 2, Y1 = a[1] + h, X2 = b[0] + w / 2, Y2 = b[1], my = (Y1 + Y2) / 2;
          path = "M" + X1 + " " + Y1 + " C" + X1 + " " + my + " " + X2 + " " + my + " " + X2 + " " + Y2;
        }
        edges.push({ from: d, to: s.id, node: el("path", { d: path, class: "pg-edge" }, gEdges) });
      });
    });
    nodes = {};
    STEPS.forEach(function (s) {
      var p = layout.pos[s.id], w = layout.w, h = layout.h;
      var g = el("g", { class: keep[s.id] || "pg-node" }, svg);
      el("rect", { class: "box", x: p[0], y: p[1], width: w, height: h, rx: 12 }, g);
      el("rect", { class: "rail", x: p[0], y: p[1] + 10, width: 4, height: h - 20, rx: 2 }, g);
      var name = el("text", { class: "name", x: p[0] + 18, y: p[1] + 28 }, g);
      name.textContent = s.id;
      var sub = el("text", { class: "sub", x: p[0] + 18, y: p[1] + 48 }, g);
      sub.textContent = keepText[s.id] || s.tool;
      el("rect", { class: "track", x: p[0] + 12, y: p[1] + h - 9, width: w - 24, height: 3, rx: 1.5 }, g);
      var bar = el("rect", { class: "bar", x: p[0] + 12, y: p[1] + h - 9, width: 0, height: 3, rx: 1.5 }, g);
      nodes[s.id] = { group: g, sub: sub, bar: bar, full: w - 24 };
    });
  }

  function setNode(id, cls, text) {
    var n = nodes[id];
    if (!n) return;
    n.group.setAttribute("class", "pg-node " + cls);
    if (text != null) n.sub.textContent = text;
  }

  function lightEdges(status) {
    edges.forEach(function (e) {
      var s = status[e.from];
      var cls = "pg-edge";
      if (PASSING[s]) cls += " lit";
      else if (BLOCKING[s]) cls += " cut";
      e.node.setAttribute("class", cls);
    });
  }

  function resetDag() {
    STEPS.forEach(function (s) {
      setNode(s.id, "", s.tool);
      var n = nodes[s.id];
      n.bar.style.transition = "none";
      n.bar.setAttribute("width", 0);
    });
    lightEdges({});
  }

  /* -------------------------------------------------------- the terminal */

  var term = document.getElementById("pgTerm");
  function line(parts) {
    var row = document.createElement("div");
    parts.forEach(function (p) {
      var span = document.createElement("span");
      if (p[1]) span.className = p[1];
      span.textContent = p[0];
      row.appendChild(span);
    });
    term.appendChild(row);
    term.scrollTop = term.scrollHeight;
  }
  function pad(text, n) { while (text.length < n) text += " "; return text; }
  function secs(n) { var s = n.toFixed(2) + "s"; while (s.length < 7) s = " " + s; return "[" + s + "] "; }

  /* --------------------------------------------------------------- a run */

  var runBtn = document.getElementById("pgRun");
  var resetBtn = document.getElementById("pgReset");

  function clearTimers() { timers.forEach(clearTimeout); timers = []; }
  function at(seconds, fn) { timers.push(setTimeout(fn, seconds * 1000)); }

  function run() {
    if (state.running) return;
    state.running = true;
    runBtn.disabled = true;
    app.classList.add("is-running");
    clearTimers();
    resetDag();
    term.innerHTML = "";

    var real = schedule(simDuration);
    var play = schedule(playDuration);
    var runNo = history.length + 1;
    var runId = "run_" + String(runNo).padStart(2, "0") + "_" + Math.random().toString(16).slice(2, 6);
    var flags = [];
    if (state.faults.flake) flags.push("GAUNTLET_FLAKE=0.3");
    line([["$ ", "prompt"], [(flags.length ? flags.join(" ") + " " : "") + "gauntlet run flows/smoke.yaml --workers 4", "cmd"]]);
    line([["gauntlet 0.2.0 · smoke_ip_block_a · " + runId + " · 4 steps", "dim"]]);

    var realBy = {};
    real.events.forEach(function (e) { realBy[e.id] = e; });
    var statusNow = {};

    play.events.forEach(function (e) {
      if (e.status !== "SKIPPED") {
        at(e.start, function () {
          setNode(e.id, "is-running", "running…");
          var n = nodes[e.id];
          n.bar.style.transition = "none";
          n.bar.setAttribute("width", 0);
          void n.bar.getBoundingClientRect();
          n.bar.style.transition = "width " + Math.max(0.05, e.end - e.start) + "s linear";
          n.bar.setAttribute("width", n.full);
        });
      }
      at(e.end, function () {
        var r = realBy[e.id];
        statusNow[e.id] = r.status;
        setNode(e.id, "is-" + r.status, r.status === "SKIPPED" ? "SKIPPED · upstream" : r.status + " · " + (r.end - r.start).toFixed(2) + "s");
        lightEdges(statusNow);
        var dur = r.status === "SKIPPED" ? 0 : r.end - r.start;
        line([[secs(dur), "dim"], [pad(r.status, 9), "st st-" + r.status.toLowerCase()], [e.id]]);
      });
    });

    at(play.total + 0.35, function () {
      var counts = { PASS: 0, WAIVED: 0, FAIL: 0, TIMEOUT: 0, SKIPPED: 0 };
      Object.keys(real.status).forEach(function (id) { counts[real.status[id]]++; });
      var ok = counts.FAIL + counts.TIMEOUT + counts.SKIPPED === 0;
      line([[""]]);
      line([["FLOW smoke_ip_block_a — ", "dim"], [ok ? "PASS" : "FAIL", ok ? "st st-pass" : "st st-fail"], [" (" + real.total.toFixed(1) + "s)", "dim"]]);
      line([["  totals: " + counts.PASS + " pass, " + counts.WAIVED + " waived, " + counts.FAIL + " fail, " + counts.TIMEOUT + " timeout, " + counts.SKIPPED + " skipped", "dim"]]);
      line([["exit " + (ok ? 0 : 1), ok ? "st st-pass" : "st st-fail"]]);
      finish({ id: runId, no: runNo, status: real.status, ok: ok, total: real.total, faults: describeFaults() });
    });
  }

  function describeFaults() {
    var f = [];
    if (state.faults.flake) f.push("flake");
    if (state.faults.hang) f.push("hang");
    if (state.faults.lint) f.push("lint");
    if (!state.waiver) f.push("no waiver");
    return f.length ? f.join(" + ") : "clean";
  }

  /* ------------------------------------------------------ history + diff */

  var histEl = document.getElementById("pgHistory");
  var diffEl = document.getElementById("pgDiff");

  function finish(record) {
    history.push(record);
    if (history.length > 6) history.shift();
    renderHistory();
    renderDiff();
    state.running = false;
    runBtn.disabled = false;
    app.classList.remove("is-running");
    runBtn.querySelector("span").textContent = "run again";
  }

  function renderHistory() {
    histEl.innerHTML = "";
    history.forEach(function (r, i) {
      var chip = document.createElement("li");
      chip.className = "pg-run " + (r.ok ? "ok" : "bad") + (i === history.length - 1 ? " latest" : "");
      chip.innerHTML = '<b></b><span></span><em></em>';
      chip.querySelector("b").textContent = r.ok ? "PASS" : "FAIL";
      chip.querySelector("span").textContent = "#" + r.no;
      chip.querySelector("em").textContent = r.faults;
      histEl.appendChild(chip);
    });
  }

  function renderDiff() {
    diffEl.innerHTML = "";
    diffEl.className = "pg-diff";
    if (history.length < 2) {
      diffEl.innerHTML = '<p class="pg-hint">Now inject a fault and run again — the diff against this run appears here.</p>';
      return;
    }
    var a = history[history.length - 2], b = history[history.length - 1];
    var buckets = { "new": [], fixed: [], still: [] };
    STEPS.forEach(function (s) {
      var fa = !!FAILING[a.status[s.id]], fb = !!FAILING[b.status[s.id]];
      if (fb && !fa) buckets["new"].push(s.id);
      else if (fb && fa) buckets.still.push(s.id);
      else if (fa && !fb) buckets.fixed.push(s.id);
    });
    var regress = buckets["new"].length > 0;
    var verdict = regress
      ? "REGRESSION (" + buckets["new"].length + " new failure" + (buckets["new"].length > 1 ? "s" : "") + ")"
      : buckets.fixed.length && !buckets.still.length ? "IMPROVED (all previous failures fixed)"
      : buckets.still.length ? "NO NEW FAILURES (" + buckets.still.length + " still failing)"
      : "CLEAN (no failures either side)";
    diffEl.className = "pg-diff " + (regress ? "bad" : "ok");

    var head = document.createElement("div");
    head.className = "pg-diff-head";
    head.innerHTML = '<code></code><strong></strong><span class="pg-exit"></span>';
    head.querySelector("code").textContent = "gauntlet diff #" + a.no + " #" + b.no;
    head.querySelector("strong").textContent = verdict;
    head.querySelector(".pg-exit").textContent = "exit " + (regress ? "1 → CI gate trips" : "0");
    diffEl.appendChild(head);

    var grid = document.createElement("div");
    grid.className = "pg-buckets";
    [["new", "new failures"], ["fixed", "fixed"], ["still", "still failing"]].forEach(function (pair) {
      var box = document.createElement("div");
      box.className = "pg-bucket " + pair[0];
      box.innerHTML = '<span class="k"></span><span class="v"></span>';
      box.querySelector(".k").textContent = pair[1] + " (" + buckets[pair[0]].length + ")";
      box.querySelector(".v").textContent = buckets[pair[0]].map(function (id) {
        // Faithful to diff.py: SKIPPED is no evidence against a step, so a
        // failure that is now skipped leaves the failing bucket. Say why.
        return pair[0] === "fixed" && b.status[id] === "SKIPPED" ? id + " (now skipped)" : id;
      }).join(", ") || "—";
      grid.appendChild(box);
    });
    diffEl.appendChild(grid);
  }

  /* ------------------------------------------------------------ controls */

  app.querySelectorAll("[data-fault]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (state.running) return;
      var key = btn.getAttribute("data-fault");
      state.faults[key] = !state.faults[key];
      btn.setAttribute("aria-pressed", String(state.faults[key]));
    });
  });
  var waiverBtn = app.querySelector("[data-waiver]");
  if (waiverBtn) {
    waiverBtn.addEventListener("click", function () {
      if (state.running) return;
      state.waiver = !state.waiver;
      waiverBtn.setAttribute("aria-pressed", String(state.waiver));
    });
  }
  runBtn.addEventListener("click", run);
  resetBtn.addEventListener("click", function () {
    if (state.running) return;
    history = [];
    renderHistory();
    diffEl.innerHTML = '<p class="pg-hint">Run the flow once to set a baseline.</p>';
    diffEl.className = "pg-diff";
    term.innerHTML = "";
    line([["$ ", "prompt"], ["# pick faults above, then: gauntlet run", "dim"]]);
    resetDag();
    runBtn.querySelector("span").textContent = "gauntlet run";
  });

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (!state.running) drawDag(); }, 120);
  });

  drawDag();
  line([["$ ", "prompt"], ["# pick faults above, then: gauntlet run", "dim"]]);
})();
