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

  // Text with [E1]/[G3] citations -> text nodes + drawer links (never innerHTML).
  var CITE = /\[([EG]\d{1,4})\]/g;
  function citeInto(node, text) {
    var s = String(text || ""), last = 0, m;
    CITE.lastIndex = 0;
    while ((m = CITE.exec(s))) {
      if (m.index > last) node.appendChild(document.createTextNode(s.slice(last, m.index)));
      node.appendChild(citeLink(m[1]));
      last = m.index + m[0].length;
    }
    if (last < s.length) node.appendChild(document.createTextNode(s.slice(last)));
    return node;
  }
  function citeLink(id) {
    var a = el("a", "cite", "[" + id + "]");
    a.href = "#ev-" + id; a.setAttribute("data-ev", id);
    return a;
  }

  // Folded panels: open the <details> that holds the URL #target.
  function openTarget() {
    if (!location.hash) return;
    var t = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    for (var n = t; n; n = n.parentElement) if (n.tagName === "DETAILS") n.open = true;
  }
  window.addEventListener("hashchange", openTarget);
  openTarget();

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
  var STEPS = ["identity", "packet", "claims", "assessed", "checked", "published"];
  var reached = -1;
  function stepEls() { return document.querySelectorAll("#live-steps li"); }
  function resetSteps() {
    reached = -1;
    Array.prototype.forEach.call(stepEls(), function (li) { li.className = ""; li.querySelector(".t").textContent = ""; });
  }
  function markStep(stage, elapsed) {
    var i = STEPS.indexOf(stage);
    if (i < 0) return;
    var lis = stepEls();
    if (lis[i]) lis[i].querySelector(".t").textContent = elapsed !== undefined && elapsed !== null ? elapsed + " s" : "";
    if (i > reached) reached = i;
  }
  function paintSteps(status) {
    var lis = stepEls();
    for (var i = 0; i < lis.length; i++) {
      var c = "";
      if (i <= reached) c = "done";
      else if (i === reached + 1) c = status === "RUNNING" ? "active" : (status === "DELIVERED" ? "" : "failed");
      lis[i].className = c;
    }
  }
  var BASIS = { crustdata_indexed_record: "Crustdata indexed record (Crunchbase-derived)" };
  function basisLabel(b) { return BASIS[b] || String(b).replace(/_/g, " "); }
  function renderFindings(res) {
    var ol = $("live-findings"), fs = (res.case && res.case.findings) || [];
    ol.textContent = "";
    fs.forEach(function (f) {
      var li = el("li"), head = el("div", "f-head");
      var label = String(f.disposition || "").replace(/_/g, " ");
      label = label.charAt(0).toUpperCase() + label.slice(1) + (f.qualified ? ", qualified" : "");
      head.appendChild(el("span", "chip disp-" + f.disposition, label));
      head.appendChild(el("span", "muted small", f.claim_id + " · " + (f.basis || []).map(basisLabel).join(" · ")));
      li.appendChild(head);
      var p = citeInto(el("p", "f-text"), f.sentence);
      (f.evidence_ids || []).forEach(function (id) {
        if (String(f.sentence || "").indexOf("[" + id + "]") < 0) { p.appendChild(document.createTextNode(" ")); p.appendChild(citeLink(id)); }
      });
      li.appendChild(p);
      ol.appendChild(li);
    });
    if (!fs.length) ol.appendChild(el("li", "muted", "No sentence passed the checks in this run."));
  }
  function beginLive(token) {
    seen = 0; resetSteps(); paintSteps("RUNNING");
    ["live-identity", "live-packet", "live-claims", "live-brief", "live-error", "live-wait", "live-desk"].forEach(function (i) { show(i, false); });
    ["live-identity", "live-packet", "live-claims"].forEach(function (i) { $(i).open = true; });
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

  function setSum(id, text) { var s = document.querySelector("#" + id + " .sum"); if (s) s.textContent = text; }
  function chip(text, cls) { $("live-chips").appendChild(el("span", "chip " + (cls || ""), text)); }

  function onEvent(e) {
    $("live-log").appendChild(el("li", "", e.elapsed + " s · " + e.stage));
    markStep(e.stage, e.elapsed);
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
      setSum("live-identity", "— " + (g.name || "?") + " · Crustdata ID " + (g.company_id || "not resolved") + " · " + (g.status || ""));
      show("live-identity", true);
    } else if (e.stage === "packet") {
      var p = document.querySelector("#live-packet .body"), ul = el("ul");
      p.textContent = "";
      (e.documents || []).forEach(function (d) { ul.appendChild(el("li", "", d.id + " · " + (d.title || "") + " · " + d.source)); });
      p.appendChild(ul);
      if (e.injection_notes) p.appendChild(el("p", "warn", e.injection_notes + " instruction-like passage(s) in fetched text ignored (data, not instructions)."));
      setSum("live-packet", "(" + (e.documents || []).length + ")");
      show("live-packet", true);
    } else if (e.stage === "claims") {
      var c = document.querySelector("#live-claims .body"), cl = el("ul");
      c.textContent = "";
      (e.claims || []).forEach(function (x) { cl.appendChild(el("li", x.selected ? "" : "muted", x.id + " (" + x.family + ", " + x.predicate + ") “" + x.quote + "”" + (x.selected ? "" : " · not selected"))); });
      if (!(e.claims || []).length) cl.appendChild(el("li", "muted", "No claims extracted."));
      c.appendChild(cl);
      var cs = e.claims || [];
      setSum("live-claims", "(" + cs.length + " extracted, " + cs.filter(function (x) { return x.selected; }).length + " selected)");
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
    paintSteps(j.status);
    if (j.status === "RUNNING") {
      var t = $("live-title"); t.textContent = "Running " + j.domain + "… ";
      t.appendChild(el("span", "elapsed", j.elapsed + " s"));
      return;
    }
    $("live-title").textContent = j.domain + " · " + j.status + (j.elapsed !== undefined ? " in " + j.elapsed + " s" : "");
    if (j.error) { $("live-error").textContent = j.error; show("live-error", true); }
    var res = j.result;
    if (res) {
      loadEvidence(res.evidence);
      var bb = document.querySelector("#live-brief .body");
      bb.innerHTML = res.brief_html || "";  // escaped server-side by md_to_html
      renderFindings(res);
      var url = res.run_url || j.run_url;
      if (url) { $("live-open").href = url; show("live-open", true); } else show("live-open", false);
      show("live-brief", true);
      var nd = (res.exceptions || []).length, dl = $("live-desk");
      dl.textContent = "Needs a person: " + nd; dl.className = "desk-line " + (nd ? "open" : "clear"); dl.hidden = false;
      $("live-status").textContent = "";
      ["live-identity", "live-packet", "live-claims"].forEach(function (i) { $(i).open = false; });
    } else if (j.run_url) {
      var a = el("a", "btn", "Open the run folder page"); a.href = j.run_url;
      $("live-status").textContent = ""; $("live-status").appendChild(a);
    }
  }

  var q = new URLSearchParams(location.search).get("token");
  if (q && $("live")) beginLive(q);
})();
