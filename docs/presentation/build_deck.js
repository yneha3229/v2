const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/root/.claude/skills/synced/413cbd54-08e5-418a-a508-b1ddf93db924_9d990523-1cfd-43d0-baba-d22ba0cc0a8b/pptx/scripts/apply_theme.js");

const THEME = { name: "Proofroom Dark", headFontFace: "Arial", bodyFontFace: "Calibri",
  colors: { dk1: "0B1020", lt1: "FFFFFF", dk2: "141D35", lt2: "A9B4D6", accent1: "22D3EE", accent2: "4F8CFF",
    accent3: "8B5CF6", accent4: "22C55E", accent5: "F5B301", accent6: "FB923C", hlink: "22D3EE", folHlink: "8B5CF6" } };
const BG = "0B1020", PANEL = "141D35", LINE = "25335C", INK = "EEF2FF", INK2 = "A9B4D6", MUTED = "6E7AA3";
const CY = "22D3EE", BL = "4F8CFF", VI = "8B5CF6", GR = "22C55E", AM = "F5B301", OR = "FB923C", RD = "EF4444";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.title = "Proofroom: ContextCon 03 finals";
pres.theme = { headFontFace: "Arial", bodyFontFace: "Calibri" };
pres.defineSlideMaster({ title: "DARK", background: { color: BG },
  objects: [{ text: { text: "PROOFROOM · ContextCon 03 · IIT Bombay", options: { x: 0.6, y: 7.0, w: 6, h: 0.3, fontSize: 10, color: MUTED, isTextBox: true } } }],
  slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: MUTED } });

const T = (s, text, sub) => {
  s.addText(text, { x: 0.6, y: 0.4, w: 12.1, h: 0.8, fontFace: "Arial", fontSize: 34, bold: true, color: INK, margin: 0, isTextBox: true });
  if (sub) s.addText(sub, { x: 0.6, y: 1.2, w: 12.1, h: 0.45, fontSize: 16, color: INK2, margin: 0, isTextBox: true });
};
const card = (s, x, y, w, h, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.15,
  fill: { color: PANEL }, line: { color: LINE, width: 1 }, objectName: name });
const num = (s, x, y, n, color) => {
  s.addShape(pres.shapes.OVAL, { x, y, w: 0.5, h: 0.5, fill: { color } });
  s.addText(String(n), { x, y, w: 0.5, h: 0.5, align: "center", valign: "middle", fontSize: 16, bold: true, color: BG, margin: 0, isTextBox: true });
};
const chartText = { catAxisLabelColor: INK2, valAxisLabelColor: MUTED, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  dataLabelFontFace: "+mn-lt", titleFontFace: "+mn-lt", catAxisLabelFontSize: 13, valAxisLabelFontSize: 11, dataLabelFontSize: 13,
  dataLabelColor: INK, valGridLine: { color: "25335C", size: 0.5 }, catGridLine: { style: "none" }, catAxisLineShow: false, valAxisLineShow: false };

// 1 · Title
pres.addSection({ title: "Opening" });
let s = pres.addSlide({ masterName: "DARK", sectionTitle: "Opening" });
s.addText([{ text: "PROOF", options: { color: INK } }, { text: "ROOM", options: { color: CY } }],
  { x: 0.8, y: 1.6, w: 11, h: 1.2, fontFace: "Arial", fontSize: 66, bold: true, margin: 0, isTextBox: true });
s.addText("Should you invest? Ask the evidence.", { x: 0.8, y: 2.9, w: 11, h: 0.8, fontSize: 32, color: INK2, margin: 0, isTextBox: true });
s.addText("Type a startup. Get a sourced investment signal and a report, in about a minute.",
  { x: 0.8, y: 3.8, w: 11, h: 0.6, fontSize: 20, italic: true, color: CY, margin: 0, isTextBox: true });
[["~1 min", "company name → report"], ["9 + live", "companies, any domain"], ["312", "automated tests"], ["14%", "median revenue error"]].forEach(([v, l], i) => {
  card(s, 0.8 + i * 3.0, 5.0, 2.7, 1.5, "stat" + i);
  s.addText(v, { x: 0.95 + i * 3.0, y: 5.1, w: 2.4, h: 0.8, fontSize: 34, bold: true, color: [CY, BL, VI, GR][i], margin: 0, isTextBox: true });
  s.addText(l, { x: 0.95 + i * 3.0, y: 5.85, w: 2.4, h: 0.5, fontSize: 14, color: INK2, margin: 0, isTextBox: true });
});
s.addNotes("Before every first meeting with a startup, someone at a fund spends about an hour checking it by hand. Proofroom does that job: type a company, get a sourced investment signal and a report in about a minute.");

// 2 · The service
pres.addSection({ title: "Problem" });
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Problem" });
T(s, "The job: an hour of checks per startup", "Analysts, associates and syndicate leads do it by hand; funds pay in time and database seats");
const qs = [["Who are the founders, really?", "Schools, prior employers, prior startups: profiles are self-reported"],
  ["How much did they raise, and is it growing?", "Totals mix in secondary sales; bands lag fast growers"],
  ["Is the market crowded?", "Funded peers, growth against peers"],
  ["What would it earn, and what does the team cost?", "No private company publishes revenue or payroll"]];
qs.forEach(([q, d], i) => { const y = 2.0 + i * 1.15; card(s, 0.6, y, 7.4, 1.0, "q" + i); num(s, 0.85, y + 0.25, i + 1, [CY, BL, VI, AM][i]);
  s.addText(q, { x: 1.55, y: y + 0.1, w: 6.3, h: 0.45, fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true });
  s.addText(d, { x: 1.55, y: y + 0.52, w: 6.3, h: 0.4, fontSize: 14, color: INK2, margin: 0, isTextBox: true }); });
card(s, 8.4, 2.0, 4.3, 4.45, "why");
s.addText("Why a chatbot gets it wrong", { x: 8.65, y: 2.15, w: 3.9, h: 0.5, fontSize: 18, bold: true, color: AM, margin: 0, isTextBox: true });
s.addText([
  { text: "It repeats the press release: the thing the investor is trying to check", options: { bullet: true, breakLine: true } },
  { text: "Linear's 'total raised' of $233M includes a $99M tender: shareholder liquidity, not capital", options: { bullet: true, breakLine: true } },
  { text: "Common names (Ramp, Clay) pull in other companies' staff", options: { bullet: true } }],
  { x: 8.65, y: 2.75, w: 3.9, h: 3.5, fontSize: 15, color: INK2, paraSpaceAfter: 10, valign: "top", margin: 0, isTextBox: true });
s.addNotes("Who pays: VC funds, angel syndicates, corp-dev teams. They pay in analyst time and in database seats that still need a person to reconcile. A summarizing chatbot repeats the press release, which is exactly what the investor wants to check.");

// 3 · How it works
pres.addSection({ title: "Product" });
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Product" });
T(s, "How it works: name in, sourced report out", "Every fact is pulled from Crustdata's graph and carries its endpoint and field");
const steps = [["Search", "Name or domain\n/company/identify", CY], ["Read the graph", "Team, growth, funding, news\n/company/enrich", BL],
  ["People", "Schools, work history, alumni counts\n/person/search", VI], ["Market", "Crowding, funded peers\n/company/search", GR],
  ["Models", "Revenue, salary, payroll\n(trained offline)", AM], ["Fixed rules", "Flags → pillars → rating\n→ check size", OR]];
steps.forEach(([h, d, c], i) => { const x = 0.6 + i * 2.1; card(s, x, 2.1, 1.9, 2.4, "step" + i);
  s.addShape(pres.shapes.OVAL, { x: x + 0.7, y: 2.3, w: 0.5, h: 0.5, fill: { color: c } });
  s.addText(String(i + 1), { x: x + 0.7, y: 2.3, w: 0.5, h: 0.5, align: "center", valign: "middle", fontSize: 16, bold: true, color: BG, margin: 0, isTextBox: true });
  s.addText(h, { x: x + 0.1, y: 2.95, w: 1.7, h: 0.45, align: "center", fontSize: 17, bold: true, color: INK, margin: 0, isTextBox: true });
  s.addText(d, { x: x + 0.1, y: 3.45, w: 1.7, h: 0.95, align: "center", fontSize: 12, color: INK2, margin: 0, valign: "top", isTextBox: true }); });
[["Live dashboard", "Rating, score, check size, revenue, growth; tabs for team, economics, market, financing, flags; 'how?' explainers", CY],
 ["Downloadable PDF", "Decision on page 1, evidence, red-flag checklist, methodology with every source", VI],
 ["Honest labels", "LIVE or replay; 'estimated' on every estimate; 'not checked' instead of zero", GR]].forEach(([h, d, c], i) => {
  const x = 0.6 + i * 4.15; card(s, x, 4.85, 3.95, 1.85, "out" + i);
  s.addText(h, { x: x + 0.25, y: 4.98, w: 3.5, h: 0.45, fontSize: 18, bold: true, color: c, margin: 0, isTextBox: true });
  s.addText(d, { x: x + 0.25, y: 5.45, w: 3.5, h: 1.15, fontSize: 14, color: INK2, margin: 0, valign: "top", isTextBox: true }); });
s.addNotes("Live demo here: type an unseen company, show the dashboard, the tabs, the how-it's-computed explainers and the PDF download.");

// 4 · Scoring: 5 pillars
pres.addSection({ title: "Method" });
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Method" });
T(s, "Scoring: 5 pillars, fixed rules", "The same rules for every company; no language model decides whether you invest");
s.addChart(pres.charts.DOUGHNUT, [{ name: "Weight", labels: ["Traction", "Team", "Market", "Financing", "Verification"], values: [30, 25, 15, 15, 15] }],
  { x: 0.4, y: 1.8, w: 4.6, h: 4.9, holeSize: 55, chartColors: [CY, BL, VI, GR, AM], showLegend: false, showValue: false, showPercent: true,
    showLabel: true, dataLabelPosition: "outEnd", dataLabelColor: INK, dataLabelFontSize: 13, dataLabelFontFace: "+mn-lt",
    showTitle: false, dataBorder: { pt: 2, color: BG } });
const pills = [["Traction 30%", "Headcount, web traffic and follower growth; growth against peers", CY],
  ["Team 25%", "Founders ID-matched; prior startups; notable employers; top-tier school for the home market (up to +14)", BL],
  ["Market 15%", "Crowding: funded peers in the category in the last 24 months", VI],
  ["Financing 15%", "How recent the last primary round is; secondary sales excluded", GR],
  ["Verification 15%", "Claims checked against the original sources (neutral 50 if not run)", AM]];
pills.forEach(([h, d, c], i) => { const y = 1.85 + i * 0.78; s.addShape(pres.shapes.OVAL, { x: 5.2, y: y + 0.12, w: 0.28, h: 0.28, fill: { color: c } });
  s.addText(h, { x: 5.6, y, w: 2.3, h: 0.5, fontSize: 16, bold: true, color: INK, margin: 0, valign: "middle", isTextBox: true });
  s.addText(d, { x: 7.85, y, w: 4.9, h: 0.7, fontSize: 13, color: INK2, margin: 0, valign: "top", isTextBox: true }); });
card(s, 5.2, 5.85, 7.55, 0.95, "rating");
s.addText([{ text: "Score → rating:  ", options: { bold: true, color: INK } },
  { text: "INVEST ≥ 70", options: { color: GR, bold: true } }, { text: "  ·  ", options: { color: MUTED } },
  { text: "ACCUMULATE ≥ 58", options: { color: AM, bold: true } }, { text: "  ·  ", options: { color: MUTED } },
  { text: "HOLD ≥ 45", options: { color: OR, bold: true } }, { text: "  ·  ", options: { color: MUTED } }, { text: "AVOID", options: { color: RD, bold: true } },
  { text: "\nA red flag caps INVEST at ACCUMULATE · a critical flag caps at HOLD · 2 critical flags force AVOID", options: { color: INK2, fontSize: 13 } }],
  { x: 5.4, y: 5.92, w: 7.2, h: 0.82, fontSize: 15, margin: 0, valign: "middle", isTextBox: true });
s.addNotes("Five weighted pillars give the score. Then flags can cap the rating, and confidence sizes the check: for example INVEST at high confidence means the full $100K; ACCUMULATE means a first tranche.");

// 5 · Revenue parameters
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Method" });
T(s, "Revenue: what drives the estimate", "Share of influence in the model trained on 126 companies (normalized model weights)");
s.addChart(pres.charts.BAR, [{ name: "Share of influence", labels: ["Company size (headcount + size bracket)", "Headcount growth", "Company age",
  "Funding (total, last round, recency)", "Location (country cost, US, tier-1 HQ)", "Category (AI, consumer, devtools, B2B, fintech)"],
  values: [49.7, 12.2, 11.2, 10.8, 8.2, 7.9] }],
  { x: 0.4, y: 1.8, w: 7.6, h: 4.9, barDir: "bar", catAxisOrientation: "maxMin", chartColors: [CY, BL, VI, GR, AM, OR], invertedColors: [CY, BL, VI, GR, AM, OR],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"%"', valAxisMaxVal: 60, valAxisLabelFormatCode: '0"%"', barGapWidthPct: 45,
    showLegend: false, showTitle: false, ...chartText, valGridLine: { color: "25335C", size: 0.5 } });
const rsteps = [["Model", "Tobit regression on 126 Crustdata revenue bands → a first estimate", CY],
  ["Correct", "Bands lag fast growers: ×2.97, learned from companies that publish revenue (scaleups only)", BL],
  ["Blend", "50% model + 50% headcount × $330K per employee (≥ 50 staff and ≥ $20M raised)", VI],
  ["Guardrails", "Revenue per employee between $20K and $1.5M; shown as a range", GR]];
rsteps.forEach(([h, d, c], i) => { const y = 1.85 + i * 1.0; num(s, 8.35, y + 0.1, i + 1, c);
  s.addText(h, { x: 9.0, y, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: INK, margin: 0, isTextBox: true });
  s.addText(d, { x: 9.0, y: y + 0.38, w: 3.8, h: 0.6, fontSize: 12.5, color: INK2, margin: 0, valign: "top", isTextBox: true }); });
card(s, 8.35, 5.9, 4.4, 0.9, "acc");
s.addText([{ text: "14% ", options: { fontSize: 26, bold: true, color: GR } }, { text: "median error · 6 of 6 within 2× on companies with public revenue (leave-one-out)", options: { fontSize: 12.5, color: INK2 } }],
  { x: 8.55, y: 5.95, w: 4.1, h: 0.8, margin: 0, valign: "middle", isTextBox: true });
s.addNotes("About half of the estimate comes from company size. Growth, age and funding are about 11-12% each; location and category about 8% each. For larger startups we blend in a revenue-per-employee benchmark, so size drives about three-quarters there. The weights are model weights, not causal effects; the correction rests on 3 companies, so we show a range.");

// 6 · Proof: results and testing
pres.addSection({ title: "Proof" });
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Proof" });
T(s, "How we know it works", "Revenue tested against public figures; claims verified with a re-checkable receipt");
s.addChart(pres.charts.BAR, [{ name: "Median error", labels: ["Crustdata band midpoint", "Model 3 (rich features)", "Model v1", "Model v2 (+ social posts)",
  "Calibrated ensemble", "Pipeline in use"], values: [78, 79, 57, 57, 31, 14] }],
  { x: 0.4, y: 1.8, w: 7.4, h: 4.9, barDir: "bar", catAxisOrientation: "maxMin", chartColors: ["3A4A7A", "3A4A7A", "3A4A7A", "3A4A7A", "3A4A7A", CY],
    invertedColors: ["3A4A7A", "3A4A7A", "3A4A7A", "3A4A7A", "3A4A7A", CY], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"',
    valAxisMaxVal: 100, valAxisLabelFormatCode: '0"%"', barGapWidthPct: 45, showLegend: false, showTitle: true, title: "Revenue: median error vs reported (lower is better)",
    titleColor: INK2, titleFontSize: 14, ...chartText });
[["312", "automated tests: API errors, identity, finance, gate, report, web", CY], ["3 / 3", "companies verified end to end with a proof receipt (Koah, Linear, Attio)", GR],
 ["Live", "unseen companies run end to end in seconds to a minute", VI]].forEach(([v, l, c], i) => {
  const y = 1.85 + i * 1.62; card(s, 8.2, y, 4.55, 1.42, "proof" + i);
  s.addText(v, { x: 8.45, y: y + 0.12, w: 1.6, h: 1.15, fontSize: 32, bold: true, color: c, margin: 0, valign: "middle", isTextBox: true });
  s.addText(l, { x: 10.1, y: y + 0.12, w: 2.5, h: 1.15, fontSize: 13.5, color: INK2, margin: 0, valign: "middle", isTextBox: true }); });
s.addNotes("Each company was scored with its own reported figure left out. Six companies is a small sample, so treat it as indicative. Tests: 312 pass.");

// 7 · Hardest case and what failed
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Proof" });
T(s, "The hardest cases, and what failed", "Numbers that are technically right but misleading");
const hard = [["Tender counted as capital", "Linear: $233M 'total raised' includes a $99M tender. We separate primary from secondary capital.", AM],
  ["Namesakes", "Ramp and Clay pull in other companies' staff. We filter founders and flag inflated headcount.", OR],
  ["Collective claims", "'Founders overlapped at Affirm, Supermove, Qualified': true for one founder. Reported as a scope correction.", VI]];
hard.forEach(([h, d, c], i) => { const y = 1.9 + i * 1.6; card(s, 0.6, y, 6.6, 1.4, "hard" + i); num(s, 0.85, y + 0.45, i + 1, c);
  s.addText(h, { x: 1.55, y: y + 0.12, w: 5.5, h: 0.45, fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true });
  s.addText(d, { x: 1.55, y: y + 0.58, w: 5.5, h: 0.75, fontSize: 14, color: INK2, margin: 0, valign: "top", isTextBox: true }); });
card(s, 7.6, 1.9, 5.15, 4.6, "failed");
s.addText("What failed, and what we kept", { x: 7.85, y: 2.05, w: 4.7, h: 0.5, fontSize: 18, bold: true, color: RD, margin: 0, isTextBox: true });
s.addText([
  { text: "Social posts in the revenue model: no gain (57% → 57%)", options: { bullet: true, breakLine: true } },
  { text: "Model 3 with 28 features overfitted 80 rows (79% error)", options: { bullet: true, breakLine: true } },
  { text: "Trusting the database 'total raised' and news dates", options: { bullet: true, breakLine: true } },
  { text: "An AI-written invest/pass verdict: rejected, not auditable", options: { bullet: true, breakLine: true } },
  { text: "Kept: the simplest pipeline that tested best (14%)", options: { bullet: true, color: GR } }],
  { x: 7.85, y: 2.65, w: 4.7, h: 3.7, fontSize: 15, color: INK2, paraSpaceAfter: 12, valign: "top", margin: 0, isTextBox: true });
s.addNotes("The hardest case is a number that is right but misleading: Linear's total includes a $99M tender. What failed: social posts and the richer Model 3 did not improve accuracy, so we kept the simplest pipeline that tested best.");

// 8 · Next + close
pres.addSection({ title: "Close" });
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Close" });
T(s, "What's next");
[["Claims check in the live dashboard", "Run the source-by-source verification for every new company, not only the three verified ones", CY],
 ["Calibrate revenue on many more companies", "The correction rests on 3 public figures today; more ground truth tightens the range", BL],
 ["Watchers", "Re-run when a founder moves or a new round is indexed, and show what changed", VI]].forEach(([h, d, c], i) => {
  const x = 0.6 + i * 4.15; card(s, x, 1.6, 3.95, 2.5, "next" + i); num(s, x + 0.25, 1.8, i + 1, c);
  s.addText(h, { x: x + 0.25, y: 2.45, w: 3.5, h: 0.75, fontSize: 18, bold: true, color: INK, margin: 0, valign: "top", isTextBox: true });
  s.addText(d, { x: x + 0.25, y: 3.2, w: 3.5, h: 0.85, fontSize: 14, color: INK2, margin: 0, valign: "top", isTextBox: true }); });
s.addText("Why not today: each needs more ground truth or model time than one day allows.", { x: 0.6, y: 4.35, w: 12.1, h: 0.45, fontSize: 15, italic: true, color: MUTED, margin: 0, isTextBox: true });
s.addText([{ text: "From a company name to a sourced investment signal, ", options: { color: INK } }, { text: "in a minute.", options: { color: CY } }],
  { x: 0.6, y: 4.95, w: 12.1, h: 1.2, fontFace: "Arial", fontSize: 30, bold: true, margin: 0, valign: "top", isTextBox: true });
s.addText("Thank you · github.com/yneha3229/v2", { x: 0.6, y: 6.3, w: 12.1, h: 0.45, fontSize: 16, color: INK2, margin: 0, isTextBox: true });
s.addNotes("Next: claims check inside the live dashboard, revenue calibrated on many more companies, and watchers. Why not today: each needs more ground truth than one day allows. Thank you.");

(async () => { await pres.writeFile({ fileName: "Proofroom_Finals.pptx" }); await applyTheme("Proofroom_Finals.pptx", THEME); console.log("ok"); })();
