// Proofroom UI: form submit, 1 s polling, progressive panels, evidence drawer, receipt.
// All source-derived text goes through textContent; only server-escaped HTML
// (brief_html from the safe markdown converter) is set as innerHTML.
(function () {
  "use strict";
  var EVIDENCE = {};
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function show(id, on) { var e = $(id); if (e) e.hidden = !on; }

  function loadEvidence(rows) {
    (rows || []).forEach(function (r) { EVIDENCE[r.id] = r; });
  }

  function openEvidence(id) {
    var r = EVIDENCE[id], body = $("drawer-body");
    if (!body) return;
    body.textContent = "";
    $("drawer-title").textContent = "Evidence " + id;
    if (!r) { body.appendChild(el("p", "muted", "No evidence row " + id + " in this run.")); }
    else {
      var src = el("p");
      src.appendChild(el("strong", "", r.kind === "graph" ? "Endpoint: " : "Source: "));
      if (r.url) {
        var a = el("a", "", r.source); a.href = r.url; a.target = "_blank"; a.rel = "noopener noreferrer nofollow";
        src.appendChild(a);
      } else src.appendChild(el("code", "", r.source));
      body.appendChild(src);
      if (r.doc_title) body.appendChild(el("p", "muted", r.doc_title));
      if (r.locator) { var l = el("p"); l.appendChild(el("strong", "", r.kind === "graph" ? "JSON path: " : "Locator: ")); l.appendChild(el("code", "", r.locator)); body.appendChild(l); }
      body.appendChild(el("blockquote", "val", r.value));
      if (r.subject_basis) body.appendChild(el("p", "small", "Subject basis: " + r.subject_basis));
      if (r.origin) body.appendChild(el("p", "small", "Origin: " + r.origin));
      var dl = el("dl", "kv");
      (r.clocks || []).forEach(function (c) {
        dl.appendChild(el("dt", "", c.clock));
        dl.appendChild(el("dd", "", c.value ? c.value + (c.precision ? " (" + c.precision + ")" : "") : "—"));
      });
      body.appendChild(el("h4", "", "Four clocks"));
      body.appendChild(dl);
    }
    $("drawer").hidden = false;
  }

  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a.cite");
    if (a) { ev.preventDefault(); openEvidence(a.getAttribute("data-ev")); }
  });
  var close = $("drawer-close");
  if (close) close.addEventListener("click", function () { $("drawer").hidden = true; });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && $("drawer")) $("drawer").hidden = true; });

  var evData = $("evidence-data");
  if (evData) { try { loadEvidence(JSON.parse(evData.textContent)); } catch (e) { /* page still works */ } }

  // ---- Proof receipt ---------------------------------------------------------------
  var rb = $("receipt-btn");
  if (rb) rb.addEventListener("click", function () {
    var out = $("receipt");
    out.hidden = false; out.textContent = "Checking…";
    fetch("/api/verify/" + encodeURIComponent(rb.dataset.case) + "/" + encodeURIComponent(rb.dataset.run))
      .then(function (r) { return r.json(); })
      .then(function (j) { out.textContent = (j.lines || []).join("\n"); out.className = "receipt " + (j.ok ? "ok" : "bad"); })
      .catch(function (e) { out.textContent = "Receipt request failed: " + e; out.className = "receipt bad"; });
  });

  // ---- Start a run -----------------------------------------------------------------
  function formData(form) {
    var d = {}, fd = new FormData(form);
    fd.forEach(function (v, k) {
      if (k === "urls") { if (String(v).trim()) (d.urls = d.urls || []).push(String(v).trim()); }
      else d[k] = v;
    });
    if (form.querySelector("[name=email]")) d.email = form.querySelector("[name=email]").checked;
    return d;
  }
  function start(body) {
    var err = $("form-error"); err.hidden = true;
    fetch("/api/runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        if (!x.ok) { err.textContent = (x.j && x.j.detail) || "Could not start the run."; err.hidden = false; return; }
        beginLive(x.j.token);
      })
      .catch(function (e) { err.textContent = "Could not start the run: " + e; err.hidden = false; });
  }
  ["run-form", "demo-form"].forEach(function (id) {
    var f = $(id);
    if (f) f.addEventListener("submit", function (e) { e.preventDefault(); start(formData(f)); });
  });

  // ---- Live progressive panels -------------------------------------------------------
  var timer = null, seen = 0;
  function beginLive(token) {
    seen = 0;
    ["live-identity", "live-packet", "live-claims", "live-brief", "live-error", "live-wait"].forEach(function (i) { show(i, false); });
    $("live-log").textContent = ""; $("live-chips").textContent = "";
    $("live-title").textContent = "Running…";
    show("live", true);
    $("live").scrollIntoView({ behavior: "smooth" });
    if (timer) clearInterval(timer);
    var poll = function () {
      fetch("/api/runs/" + encodeURIComponent(token)).then(function (r) { return r.json(); })
        .then(function (j) { render(j); if (j.status !== "RUNNING") { clearInterval(timer); timer = null; } })
        .catch(function () { /* transient; next tick retries */ });
    };
    poll(); timer = setInterval(poll, 1000);
  }

  function chip(text, cls) { $("live-chips").appendChild(el("span", "chip " + (cls || ""), text)); }

  function onEvent(e) {
    $("live-log").appendChild(el("li", "", e.elapsed + " s · " + e.stage));
    if (e.stage === "start") {
      chip(e.mode, "mode-" + String(e.mode).toLowerCase());
      chip("model: " + e.model_source);
      chip(e.profile + (e.profile === "FAST" ? " · reduced checking" : ""), e.profile === "FAST" ? "warn" : "");
    } else if (e.stage === "identity") {
      var b = document.querySelector("#live-identity .body"), g = e.g1 || {};
      b.textContent = "";
      b.appendChild(el("p", "", (g.name || "?") + " · Crustdata ID " + (g.company_id || "not resolved") + " · " + (g.status || "")));
      b.appendChild(el("p", "muted", g.basis || ""));
      if ((g.excluded || []).length) b.appendChild(el("p", "small", "Excluded namesakes: " + g.excluded.map(function (x) { return x.name || x.id || JSON.stringify(x); }).join(", ")));
      b.appendChild(el("p", "", "Team in graph: " + ((e.team || []).join(", ") || "none")));
      show("live-identity", true);
    } else if (e.stage === "packet") {
      var p = document.querySelector("#live-packet .body"), ul = el("ul");
      p.textContent = "";
      (e.documents || []).forEach(function (d) { ul.appendChild(el("li", "", d.id + " · " + (d.title || "") + " · " + d.source)); });
      p.appendChild(ul);
      if (e.injection_notes) p.appendChild(el("p", "warn", e.injection_notes + " instruction-like passage(s) in fetched text ignored (data, not instructions)."));
      show("live-packet", true);
    } else if (e.stage === "claims") {
      var c = document.querySelector("#live-claims .body"), cl = el("ul");
      c.textContent = "";
      (e.claims || []).forEach(function (x) { cl.appendChild(el("li", x.selected ? "" : "muted", x.id + " (" + x.family + ", " + x.predicate + ") “" + x.quote + "”" + (x.selected ? "" : " · not selected"))); });
      if (!(e.claims || []).length) cl.appendChild(el("li", "muted", "No claims extracted."));
      c.appendChild(cl);
      show("live-claims", true);
    } else if (e.stage === "assessed" || e.stage === "checked") {
      $("live-status").textContent = e.stage === "assessed" ? e.findings + " finding(s) assessed; running the code gate and sentence check…"
        : e.kept + " sentence(s) kept, " + e.suppressed + " suppressed by the checks.";
    }
  }

  function render(j) {
    var ev = j.events || [];
    for (; seen < ev.length; seen++) onEvent(ev[seen]);
    var w = $("live-wait");
    if (j.waiting_for_model) { w.textContent = "Waiting for the model (agent session) — call " + j.waiting_for_model; w.hidden = false; }
    else w.hidden = true;
    if (j.status === "RUNNING") { $("live-title").textContent = "Running " + j.domain + "… " + j.elapsed + " s"; return; }
    $("live-title").textContent = j.domain + " · " + j.status;
    if (j.error) { $("live-error").textContent = j.error; show("live-error", true); }
    var res = j.result;
    if (res) {
      loadEvidence(res.evidence);
      var bb = document.querySelector("#live-brief .body");
      bb.innerHTML = res.brief_html || "";  // escaped server-side by md_to_html
      var url = res.run_url || j.run_url;
      if (url) $("live-open").href = url; else show("live-open", false);
      show("live-brief", true);
      $("live-status").textContent = "Needs a person: " + (res.exceptions || []).length;
    } else if (j.run_url) {
      var a = el("a", "btn", "Open the run folder page"); a.href = j.run_url;
      $("live-status").textContent = ""; $("live-status").appendChild(a);
    }
  }

  var q = new URLSearchParams(location.search).get("token");
  if (q && $("live")) beginLive(q);
})();
