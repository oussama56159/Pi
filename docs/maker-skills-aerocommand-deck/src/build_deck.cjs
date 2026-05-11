const path = require("node:path");
const fs = require("node:fs");
require("module").Module._initPaths();

const pptxgen = require("pptxgenjs");
const sharp = require("sharp");

const workspace = path.resolve(__dirname, "..");
const repo = path.resolve(workspace, "..", "..");
const outputDir = path.join(workspace, "output");
const scratchDir = path.join(workspace, "scratch");
const previewDir = path.join(scratchDir, "previews");
fs.mkdirSync(outputDir, { recursive: true });
fs.mkdirSync(previewDir, { recursive: true });

const assets = {
  makerLogo: path.join(repo, "dashboard", "public", "landing", "logos", "makerskills.png"),
  screen1: path.join(repo, "dashboard", "public", "landing", "screen-1.png"),
  screen2: path.join(repo, "dashboard", "public", "landing", "screen-2.png"),
  appIcon: path.join(repo, "appicon.png"),
};

function imageData(imagePath) {
  const ext = path.extname(imagePath).toLowerCase();
  const mime = ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : "image/png";
  return `data:${mime};base64,${fs.readFileSync(imagePath).toString("base64")}`;
}

const assetData = {
  screen1: imageData(assets.screen1),
  screen2: imageData(assets.screen2),
};

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Maker Skills";
pptx.subject = "Commercial presentation for AeroCommand";
pptx.title = "AeroCommand Commercial Presentation";
pptx.company = "Maker Skills";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";
pptx.margin = 0;

const C = {
  ink: "132238",
  muted: "607083",
  cloud: "F6FAFB",
  navy: "102A43",
  deep: "071B2E",
  teal: "0E7C86",
  mint: "35B88F",
  lime: "B9E769",
  coral: "FF7A59",
  yellow: "F6C85F",
  white: "FFFFFF",
  line: "D8E4E8",
};

const W = 13.333;
const H = 7.5;

const slides = [
  {
    kind: "cover",
    kicker: "Maker Skills startup presentation",
    title: "AeroCommand",
    subtitle: "A practical drone monitoring service for farms, fields, and cooperatives",
    footer: "Commercial presentation | May 2026",
  },
  {
    kind: "intro",
    kicker: "1. Introduction",
    title: "Maker Skills builds field technology farmers can actually use",
    bullets: [
      ["Team", "A startup focused on smart agriculture, drones, and mobile IoT"],
      ["Project", "AeroCommand, a web and mobile platform for drone-assisted farm monitoring"],
      ["Purpose", "Show how the product saves time, improves visibility, and becomes a service"],
    ],
  },
  {
    kind: "problem",
    kicker: "2. Problem / storytelling",
    title: "A farmer cannot be everywhere at once",
    lead: "Large fields, livestock areas, irrigation lines, and equipment zones are hard to check every day.",
    problems: [
      "A broken fence may be noticed only after animals escape",
      "Dry zones or crop stress can spread before anyone sees them",
      "Field checks consume hours of walking, driving, and fuel",
      "The farm owner often has no live view when away from the land",
    ],
    videoNote: "Video idea: morning field check by truck vs. one drone mission visible on the phone.",
  },
  {
    kind: "problem",
    kicker: "2. Problem / storytelling",
    title: "Delayed detection turns small issues into expensive losses",
    lead: "Most farm problems start small. The cost grows when the information arrives late.",
    problems: [
      "Livestock leaves a pasture through a small opening",
      "Irrigation failure creates dry patches before the next visit",
      "Disease or pests spread from one visible area to a whole row",
      "The farmer spends time checking areas that are still normal",
    ],
    videoNote: "Short scene: one missed field problem becomes a repair, treatment, or lost-animal event.",
  },
  {
    kind: "features",
    kicker: "2. Farmer workflow",
    title: "The daily job: inspect more land with less uncertainty",
    features: [
      ["Morning check", "Launch or schedule a route over fields, fences, or livestock zones"],
      ["Live view", "See drone status, location, battery, and mission progress from the dashboard"],
      ["Alert moment", "Receive a signal when something needs attention"],
      ["Action", "Send a worker, adjust irrigation, inspect a zone, or repeat the mission"],
    ],
  },
  {
    kind: "solution",
    kicker: "3. Your solution",
    title: "AeroCommand turns drones into a farm monitoring service",
    steps: [
      ["Drone in the field", "Collects position, battery, camera, and mission status"],
      ["Cloud platform", "Stores history, manages missions, commands, alerts, and live updates"],
      ["Farmer interface", "Web dashboard and mobile app for decisions in the office or on-site"],
    ],
    features: ["Live map", "Scheduled routes", "Alerts", "Mobile access", "AI vision", "History"],
  },
  {
    kind: "features",
    kicker: "3. Main features",
    title: "Live farm visibility without a technical control room",
    features: [
      ["Fleet map", "Know where each drone is and whether it is ready, flying, or offline"],
      ["Telemetry", "Battery, GPS, speed, altitude, signal, and vehicle health in real time"],
      ["Web + mobile", "Use the dashboard from the office and the phone from the field"],
      ["History", "Review past flights, alerts, and vehicle activity"],
    ],
  },
  {
    kind: "features",
    kicker: "3. Main features",
    title: "Automated missions make farm checks repeatable",
    features: [
      ["Field routes", "Plan coverage paths for olive groves, cereals, orchards, or pastures"],
      ["Fence lines", "Repeat perimeter inspection without driving the whole boundary"],
      ["Irrigation zones", "Check dry areas and water distribution from above"],
      ["Progress tracking", "See whether the mission is pending, running, completed, or failed"],
    ],
  },
  {
    kind: "features",
    kicker: "3. Main features",
    title: "Alerts help farmers react before problems grow",
    features: [
      ["Livestock", "Flag animals outside an expected area or separated from the herd"],
      ["Security", "Notice people or vehicles in restricted farm zones"],
      ["Operations", "Detect low battery, lost connection, or mission interruption"],
      ["Evidence", "Keep timestamped alert history for follow-up and accountability"],
    ],
  },
  {
    kind: "features",
    kicker: "3. Main features",
    title: "AI vision adds an extra pair of eyes",
    features: [
      ["Detection", "Optional object detection for livestock, people, vehicles, or field objects"],
      ["Counting", "Support visual confirmation when checking animals or assets"],
      ["Zone awareness", "Connect detections to areas that matter on the farm"],
      ["Human control", "AI supports decisions; the farmer still confirms what action to take"],
    ],
  },
  {
    kind: "target",
    kicker: "4. Target market",
    title: "Primary buyers: farms that lose time in repeated field checks",
    segments: [
      ["Small farms", "1-2 drones for daily checks, alerts, and basic monitoring"],
      ["Medium farms", "Several zones, multiple missions, livestock and crop monitoring"],
      ["Cooperatives", "Shared drone service across many farmers with centralized support"],
    ],
    note: "The customer is practical: they care about fewer unnecessary trips, faster reaction, and a system that does not require a full IT team.",
  },
  {
    kind: "target",
    kicker: "4. Target market",
    title: "Tunisian agriculture gives us focused first use cases",
    segments: [
      ["Olive groves", "Tree health, irrigation checks, harvest preparation, perimeter monitoring"],
      ["Date palms", "Large-area inspection, pest spotting, worker coordination"],
      ["Cereals", "Crop stress, dry patches, growth tracking, harvest readiness"],
    ],
    note: "The product can sound advanced, but the first value is simple: see more of the farm, more often.",
  },
  {
    kind: "target",
    kicker: "4. Target market",
    title: "The buyer ecosystem extends beyond one farmer",
    segments: [
      ["Direct customer", "Farm owners and managers who need visibility over their land"],
      ["Service provider", "Drone operators offering monitoring as a service"],
      ["Institutional channel", "Cooperatives, training centers, smart-agriculture programs"],
    ],
    note: "This lets Maker Skills sell both directly and through trusted local organizations.",
  },
  {
    kind: "comparison",
    kicker: "5. Competitive advantage",
    title: "AeroCommand is more farm-ready than generic drone tools",
    rows: [
      ["Criterion", "Typical ground station", "Generic drone app", "AeroCommand"],
      ["Main user", "Pilot or technician", "Consumer drone owner", "Farmer, cooperative, service team"],
      ["Farm workflow", "Manual setup", "Limited scheduling", "Repeatable routes and alerts"],
      ["Data access", "Local session", "Vendor dependent", "Cloud history and mobile view"],
      ["Support model", "Technical user", "Online help", "Local training and deployment"],
    ],
  },
  {
    kind: "comparison",
    kicker: "5. Competitive advantage",
    title: "Our advantage is simplicity, service, and local adaptation",
    rows: [
      ["Need", "Current habit", "Risk", "AeroCommand response"],
      ["Daily inspection", "Walking or driving", "Slow and incomplete", "Scheduled drone routes"],
      ["Problem detection", "Only after visible damage", "Late reaction", "Alerts and camera evidence"],
      ["Farm access", "Owner must be present", "Low visibility", "Mobile dashboard"],
      ["Adoption", "Complex tech setup", "Low trust", "Training and local support"],
    ],
  },
  {
    kind: "business",
    kicker: "6. Business model",
    title: "Product-as-a-service keeps the offer simple",
    plans: [
      ["Starter", "1-2 drones", "Dashboard, mobile access, live map, basic telemetry history"],
      ["Pro", "3-10 drones", "Mission planning, alerts, AI detection, and priority support"],
      ["Cooperative", "Shared service", "Multi-farm organization, training, custom support, SLA"],
    ],
    extra: ["Setup and edge installation", "Operator training", "Optional AI analytics", "Support and maintenance"],
  },
  {
    kind: "business",
    kicker: "6. Business model",
    title: "Revenue grows around the service, not only the software",
    plans: [
      ["Subscription", "Recurring", "Dashboard, mobile app, telemetry history, alerts"],
      ["Deployment", "One-time", "Drone connection, edge agent setup, onboarding"],
      ["Add-ons", "Optional", "AI detection, custom reports, extra users, integrations"],
    ],
    extra: ["This makes pricing understandable for farmers and scalable for Maker Skills."],
  },
  {
    kind: "marketing",
    kicker: "7. Marketing strategy",
    title: "Sell through trust, demos, and local proof",
    channels: [
      ["Field demos", "Show a real route over a farm and an alert on the phone"],
      ["Cooperatives", "Use trusted local groups to reach farmers faster"],
      ["Drone sellers", "Bundle AeroCommand as the software layer for farm customers"],
      ["Events", "Agricultural expos, university incubators, smart agriculture programs"],
    ],
  },
  {
    kind: "marketing",
    kicker: "7. Marketing strategy",
    title: "Digital marketing should show real farm value fast",
    channels: [
      ["Facebook groups", "Short clips: field route, live map, alert, result"],
      ["Before / after", "Manual inspection vs. drone-assisted monitoring"],
      ["Farmer stories", "Use simple cases: dry zone found, fence checked, herd located"],
      ["B2B outreach", "LinkedIn and direct visits for cooperatives and service providers"],
    ],
  },
  {
    kind: "demo",
    kicker: "8. Demo / visuals",
    title: "Demo: from farm map to operational decision",
    captions: ["Operations dashboard", "Smart farming product page"],
    images: [assets.screen1, assets.screen2],
    callouts: ["Live fleet status", "Farm route planning", "Mobile + web access"],
  },
  {
    kind: "features",
    kicker: "8. Demo / visuals",
    title: "Demo storyline for the presentation",
    features: [
      ["Step 1", "Open the dashboard and select the farm vehicle"],
      ["Step 2", "Show location, battery, and telemetry on the live map"],
      ["Step 3", "Launch or review a monitoring mission"],
      ["Step 4", "Show an alert and explain what action the farmer takes"],
    ],
  },
  {
    kind: "solution",
    kicker: "9. Deployment",
    title: "What installation looks like for a farm customer",
    steps: [
      ["Connect", "Pair drone or robot telemetry with the edge agent"],
      ["Configure", "Create farm zones, routes, users, and alert rules"],
      ["Train", "Teach the farmer or operator the daily workflow"],
    ],
    features: ["Setup", "Training", "Support", "Updates", "Maintenance", "Reports"],
  },
  {
    kind: "features",
    kicker: "9. Impact",
    title: "The business promise is practical, not futuristic",
    features: [
      ["Less wasted time", "Reduce repeated manual checks across the same routes"],
      ["Faster reaction", "Find field problems before they become bigger losses"],
      ["Better coordination", "Give workers clearer information before they go on-site"],
      ["More confidence", "Keep visibility over remote zones even when the owner is away"],
    ],
  },
  {
    kind: "target",
    kicker: "9. Roadmap",
    title: "Next steps make the farm value stronger",
    segments: [
      ["Short term", "Polish dashboard demo, mobile alerts, and mission workflows"],
      ["Pilot", "Run controlled farm demonstrations with one or two local partners"],
      ["Expansion", "Add farm reports, AI detection tuning, and cooperative management"],
    ],
    note: "The goal is to prove value in the field before scaling the commercial offer.",
  },
  {
    kind: "conclusion",
    kicker: "10. Conclusion",
    title: "AeroCommand helps farmers see more, sooner",
    summary: [
      ["Problem", "Farmers lose time and money when field information arrives late"],
      ["Solution", "Drone monitoring with live maps, missions, alerts, and mobile access"],
      ["Why it matters", "More visibility, faster reaction, and a practical path to smart agriculture"],
    ],
  },
  {
    kind: "qa",
    kicker: "11. Q&A",
    title: "Thank you for your attention.",
    subtitle: "Do you have any questions?",
  },
];

function addBg(slide, color = C.cloud) {
  slide.background = { color };
}

function addFooter(slide, n, dark = false) {
  if (!dark) {
    slide.addShape(pptx.ShapeType.line, { x: 0, y: 6.78, w: W, h: 0, line: { color: "DBEEE8", width: 1.2, transparency: 8 } });
    slide.addShape(pptx.ShapeType.line, { x: 7.6, y: 6.95, w: 1.6, h: -0.35, line: { color: C.mint, width: 1.1, transparency: 28 } });
    slide.addShape(pptx.ShapeType.line, { x: 8.2, y: 6.95, w: 1.9, h: -0.35, line: { color: C.teal, width: 1.0, transparency: 38 } });
    slide.addShape(pptx.ShapeType.line, { x: 8.9, y: 6.95, w: 2.2, h: -0.35, line: { color: C.yellow, width: 0.9, transparency: 42 } });
  }
  slide.addText("Maker Skills | AeroCommand", {
    x: 0.55, y: 7.03, w: 4.5, h: 0.18,
    margin: 0, fontFace: "Aptos", fontSize: 7.8,
    color: dark ? "B5C8D0" : C.muted,
    breakLine: false, fit: "shrink",
  });
  slide.addText(String(n).padStart(2, "0"), {
    x: 12.18, y: 7.02, w: 0.6, h: 0.18,
    margin: 0, fontFace: "Aptos", fontSize: 7.8,
    align: "right", color: dark ? "B5C8D0" : C.muted,
    breakLine: false, fit: "shrink",
  });
}

function addKicker(slide, txt, dark = false) {
  slide.addText(txt.toUpperCase(), {
    x: 0.72, y: 0.52, w: 4.5, h: 0.28,
    margin: 0, fontFace: "Aptos", fontSize: 9.5, bold: true,
    color: dark ? C.lime : C.teal, charSpace: 1.2,
    breakLine: false, fit: "shrink",
  });
}

function title(slide, text, y = 0.9, color = C.ink, size = 30, w = 10.8) {
  slide.addText(text, {
    x: 0.72, y, w, h: 0.92,
    margin: 0, fontFace: "Aptos Display", fontSize: size, bold: true,
    color, breakLine: false, fit: "shrink",
  });
}

function pill(slide, text, x, y, w, color = C.teal, fill = "E8F6F2") {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.34,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: fill, transparency: 100 },
  });
  slide.addText(text, {
    x: x + 0.12, y: y + 0.08, w: w - 0.24, h: 0.12,
    margin: 0, fontSize: 8.5, bold: true, color, fit: "shrink",
    breakLine: false, align: "center",
  });
}

function bullet(slide, txt, x, y, w, color = C.ink) {
  slide.addShape(pptx.ShapeType.ellipse, {
    x, y: y + 0.07, w: 0.11, h: 0.11,
    fill: { color: C.mint },
    line: { color: C.mint },
  });
  slide.addText(txt, {
    x: x + 0.22, y, w, h: 0.28,
    margin: 0, fontSize: 14.2, color,
    breakLine: false, fit: "shrink",
  });
}

function addImage(slide, imagePath, x, y, w, h, line = C.line) {
  slide.addImage({ path: imagePath, x, y, w, h });
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: C.white, transparency: 100 },
    line: { color: line, width: 1 },
  });
}

function cover(s, spec) {
  addBg(s, C.deep);
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: H, fill: { color: C.deep }, line: { transparency: 100 } });
  s.addShape(pptx.ShapeType.arc, { x: 6.4, y: -1.9, w: 7.8, h: 7.8, adjustPoint: 0.2, fill: { color: "0E7C86", transparency: 10 }, line: { transparency: 100 }, rotate: 20 });
  s.addShape(pptx.ShapeType.chevron, { x: 7.85, y: 1.05, w: 4.8, h: 2.6, fill: { color: C.mint, transparency: 8 }, line: { transparency: 100 }, rotate: -7 });
  s.addShape(pptx.ShapeType.line, { x: 7.05, y: 4.83, w: 4.75, h: -2.3, line: { color: C.lime, width: 2.2, transparency: 12, beginArrowType: "none", endArrowType: "triangle" } });
  s.addImage({ path: assets.makerLogo, x: 0.72, y: 0.58, w: 1.25, h: 0.45 });
  s.addText(spec.kicker.toUpperCase(), { x: 0.72, y: 1.45, w: 4.3, h: 0.25, margin: 0, fontSize: 9.8, bold: true, color: C.lime, charSpace: 1.3, fit: "shrink" });
  s.addText(spec.title, { x: 0.72, y: 2.0, w: 7.2, h: 0.9, margin: 0, fontFace: "Aptos Display", fontSize: 43, bold: true, color: C.white, fit: "shrink" });
  s.addText(spec.subtitle, { x: 0.72, y: 3.05, w: 5.4, h: 0.7, margin: 0, fontSize: 19, color: "D9E9EC", breakLine: false, fit: "shrink" });
  s.addText(spec.footer, { x: 0.72, y: 6.55, w: 4.5, h: 0.25, margin: 0, fontSize: 10, color: "B5C8D0", fit: "shrink" });
}

function intro(s, spec, n) {
  addBg(s); addKicker(s, spec.kicker); title(s, spec.title, 0.95, C.ink, 29, 10.8);
  spec.bullets.forEach((b, i) => {
    const y = 2.25 + i * 1.22;
    s.addText(b[0], { x: 0.9, y, w: 1.8, h: 0.35, margin: 0, fontSize: 16, bold: true, color: C.teal, fit: "shrink" });
    s.addShape(pptx.ShapeType.line, { x: 2.75, y: y + 0.18, w: 0.72, h: 0, line: { color: C.coral, width: 1.7 } });
    s.addText(b[1], { x: 3.7, y: y - 0.05, w: 7.8, h: 0.46, margin: 0, fontSize: 18.5, color: C.ink, fit: "shrink", breakLine: false });
  });
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 6.52, w: W, h: 0.33, fill: { color: C.teal }, line: { transparency: 100 } });
  addFooter(s, n);
}

function problem(s, spec, n) {
  addBg(s, "FFF8F3"); addKicker(s, spec.kicker); title(s, spec.title, 0.88, C.ink, 29, 10.6);
  s.addText(spec.lead, { x: 0.75, y: 1.95, w: 6.45, h: 0.48, margin: 0, fontSize: 17, color: C.muted, fit: "shrink" });
  spec.problems.forEach((p, i) => bullet(s, p, 0.92, 2.82 + i * 0.58, 5.8));
  s.addShape(pptx.ShapeType.rect, { x: 8.1, y: 1.45, w: 3.4, h: 4.65, fill: { color: C.deep }, line: { color: C.deep } });
  s.addShape(pptx.ShapeType.line, { x: 8.58, y: 5.5, w: 2.28, h: -3.15, line: { color: C.lime, width: 2.5, endArrowType: "triangle" } });
  s.addShape(pptx.ShapeType.line, { x: 8.62, y: 3.35, w: 2.12, h: 0.55, line: { color: C.coral, width: 1.8 } });
  s.addShape(pptx.ShapeType.line, { x: 8.72, y: 4.4, w: 1.9, h: -0.3, line: { color: C.mint, width: 1.8 } });
  s.addText("Story hook", { x: 8.45, y: 1.95, w: 2.6, h: 0.28, margin: 0, fontSize: 11, bold: true, color: C.lime, align: "center" });
  s.addText(spec.videoNote, { x: 8.38, y: 5.48, w: 2.83, h: 0.42, margin: 0, fontSize: 9.5, color: "E6F4F1", fit: "shrink", breakLine: false, align: "center" });
  addFooter(s, n);
}

function solution(s, spec, n) {
  addBg(s); addKicker(s, spec.kicker); title(s, spec.title, 0.86, C.ink, 29, 11.2);
  const xs = [0.82, 4.7, 8.58];
  spec.steps.forEach((step, i) => {
    const x = xs[i];
    s.addShape(pptx.ShapeType.ellipse, { x: x + 1.02, y: 2.1, w: 1.05, h: 1.05, fill: { color: [C.teal, C.mint, C.coral][i] }, line: { transparency: 100 } });
    s.addText(String(i + 1), { x: x + 1.33, y: 2.35, w: 0.42, h: 0.28, margin: 0, fontSize: 19, bold: true, color: C.white, align: "center", fit: "shrink" });
    s.addText(step[0], { x, y: 3.45, w: 3.05, h: 0.28, margin: 0, fontSize: 16, bold: true, color: C.ink, align: "center", fit: "shrink" });
    s.addText(step[1], { x, y: 3.9, w: 3.05, h: 0.72, margin: 0, fontSize: 12.6, color: C.muted, align: "center", breakLine: false, fit: "shrink" });
    if (i < 2) s.addShape(pptx.ShapeType.line, { x: x + 2.58, y: 2.62, w: 1.1, h: 0, line: { color: C.line, width: 2, endArrowType: "triangle" } });
  });
  spec.features.forEach((f, i) => pill(s, f, 1.0 + (i % 3) * 3.75, 5.38 + Math.floor(i / 3) * 0.52, 2.62, i % 2 ? C.teal : C.ink, i % 2 ? "E8F6F2" : "EFF4F7"));
  addFooter(s, n);
}

function features(s, spec, n) {
  addBg(s, "F8FBF6"); addKicker(s, spec.kicker); title(s, spec.title, 0.9, C.ink, 30, 10.6);
  spec.features.forEach((f, i) => {
    const x = i % 2 === 0 ? 0.82 : 7.0;
    const y = i < 2 ? 2.0 : 4.55;
    s.addShape(pptx.ShapeType.line, { x, y: y + 0.1, w: 0.8, h: 0, line: { color: [C.mint, C.teal, C.coral, C.yellow][i], width: 4 } });
    s.addText(f[0], { x, y: y + 0.42, w: 5.1, h: 0.35, margin: 0, fontSize: 18, bold: true, color: C.ink, fit: "shrink" });
    s.addText(f[1], { x, y: y + 0.9, w: 5.25, h: 0.52, margin: 0, fontSize: 13.2, color: C.muted, breakLine: false, fit: "shrink" });
  });
  addFooter(s, n);
}

function target(s, spec, n) {
  addBg(s); addKicker(s, spec.kicker); title(s, spec.title, 0.9, C.ink, 29, 10.6);
  const ys = [2.1, 3.42, 4.74];
  spec.segments.forEach((seg, i) => {
    s.addText(seg[0], { x: 0.95, y: ys[i], w: 1.35, h: 0.28, margin: 0, fontSize: 11, bold: true, color: [C.teal, C.coral, C.mint][i], fit: "shrink" });
    s.addShape(pptx.ShapeType.line, { x: 2.45, y: ys[i] + 0.13, w: 0.85, h: 0, line: { color: C.line, width: 1.2 } });
    s.addText(seg[1], { x: 3.48, y: ys[i] - 0.04, w: 7.6, h: 0.38, margin: 0, fontSize: 18, color: C.ink, fit: "shrink", breakLine: false });
  });
  s.addText(spec.note, { x: 0.95, y: 6.04, w: 10.8, h: 0.42, margin: 0, fontSize: 14.8, italic: true, color: C.teal, fit: "shrink" });
  addFooter(s, n);
}

function comparison(s, spec, n) {
  addBg(s, "F7FAFC"); addKicker(s, spec.kicker); title(s, spec.title, 0.88, C.ink, 28, 11.1);
  const x = 0.72, y = 2.0, widths = [2.0, 2.8, 2.8, 3.8], rowH = 0.72;
  spec.rows.forEach((row, r) => {
    let cx = x;
    row.forEach((cell, c) => {
      const isHead = r === 0;
      s.addShape(pptx.ShapeType.rect, {
        x: cx, y: y + r * rowH, w: widths[c], h: rowH,
        fill: { color: isHead ? (c === 3 ? C.teal : C.navy) : (c === 3 ? "E9F7F3" : C.white) },
        line: { color: C.line, width: 0.7 },
      });
      s.addText(cell, {
        x: cx + 0.12, y: y + r * rowH + 0.2, w: widths[c] - 0.24, h: 0.28,
        margin: 0, fontSize: isHead ? 10.5 : 10.2, bold: isHead || c === 3,
        color: isHead ? C.white : (c === 3 ? C.teal : C.ink),
        fit: "shrink", breakLine: false,
      });
      cx += widths[c];
    });
  });
  addFooter(s, n);
}

function business(s, spec, n) {
  addBg(s); addKicker(s, spec.kicker); title(s, spec.title, 0.9, C.ink, 29, 10.8);
  spec.plans.forEach((plan, i) => {
    const x = 0.82 + i * 4.0;
    s.addShape(pptx.ShapeType.rect, { x, y: 2.04, w: 3.3, h: 2.4, fill: { color: [C.navy, C.teal, C.mint][i] }, line: { transparency: 100 } });
    s.addText(plan[0], { x: x + 0.22, y: 2.3, w: 2.7, h: 0.34, margin: 0, fontSize: 18, bold: true, color: C.white, fit: "shrink" });
    s.addText(plan[1], { x: x + 0.22, y: 2.83, w: 2.8, h: 0.28, margin: 0, fontSize: 11.5, bold: true, color: "E8F6F2", fit: "shrink" });
    s.addText(plan[2], { x: x + 0.22, y: 3.32, w: 2.75, h: 0.58, margin: 0, fontSize: 10.7, color: C.white, breakLine: false, fit: "shrink" });
  });
  spec.extra.forEach((e, i) => bullet(s, e, 1.05 + i * 4.02, 5.55, 2.9));
  addFooter(s, n);
}

function marketing(s, spec, n) {
  addBg(s, "FFFDF7"); addKicker(s, spec.kicker); title(s, spec.title, 0.9, C.ink, 30, 10.8);
  spec.channels.forEach((ch, i) => {
    const y = 2.0 + i * 1.05;
    s.addText(ch[0], { x: 0.92, y, w: 2.2, h: 0.3, margin: 0, fontSize: 17, bold: true, color: [C.teal, C.coral, C.mint, C.navy][i], fit: "shrink" });
    s.addText(ch[1], { x: 3.42, y: y - 0.02, w: 7.8, h: 0.34, margin: 0, fontSize: 16, color: C.ink, fit: "shrink", breakLine: false });
  });
  s.addShape(pptx.ShapeType.line, { x: 0.92, y: 6.18, w: 10.9, h: 0, line: { color: C.yellow, width: 2.2 } });
  addFooter(s, n);
}

function demo(s, spec, n) {
  addBg(s, "F6FAFB"); addKicker(s, spec.kicker); title(s, spec.title, 0.85, C.ink, 30, 10.7);
  addImage(s, spec.images[0], 0.82, 1.78, 5.45, 3.3);
  addImage(s, spec.images[1], 6.95, 1.78, 5.45, 3.3);
  s.addText(spec.captions[0], { x: 0.82, y: 5.24, w: 5.45, h: 0.25, margin: 0, fontSize: 11, bold: true, color: C.ink, align: "center", fit: "shrink" });
  s.addText(spec.captions[1], { x: 6.95, y: 5.24, w: 5.45, h: 0.25, margin: 0, fontSize: 11, bold: true, color: C.ink, align: "center", fit: "shrink" });
  spec.callouts.forEach((c, i) => pill(s, c, 1.3 + i * 3.72, 6.03, 2.55, [C.teal, C.ink, C.coral][i], ["E8F6F2", "EFF4F7", "FFF0EA"][i]));
  addFooter(s, n);
}

function conclusion(s, spec, n) {
  addBg(s, C.deep); addKicker(s, spec.kicker, true);
  title(s, spec.title, 0.95, C.white, 31, 11.2);
  spec.summary.forEach((item, i) => {
    const x = 0.95 + i * 4.05;
    s.addShape(pptx.ShapeType.line, { x, y: 2.55, w: 1.0, h: 0, line: { color: [C.coral, C.lime, C.mint][i], width: 4 } });
    s.addText(item[0], { x, y: 3.08, w: 3.2, h: 0.34, margin: 0, fontSize: 17, bold: true, color: C.white, fit: "shrink" });
    s.addText(item[1], { x, y: 3.6, w: 3.35, h: 0.72, margin: 0, fontSize: 12.8, color: "D8E8EC", breakLine: false, fit: "shrink" });
  });
  addFooter(s, n, true);
}

function qa(s, spec) {
  addBg(s, C.deep);
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: H, fill: { color: C.deep }, line: { transparency: 100 } });
  s.addShape(pptx.ShapeType.arc, { x: 7.1, y: -2.0, w: 7.2, h: 7.2, fill: { color: C.teal, transparency: 18 }, line: { transparency: 100 }, rotate: 15 });
  s.addImage({ path: assets.makerLogo, x: 0.72, y: 0.58, w: 1.25, h: 0.45 });
  s.addText(spec.kicker.toUpperCase(), { x: 0.72, y: 1.7, w: 3.1, h: 0.25, margin: 0, fontSize: 9.8, bold: true, color: C.lime, charSpace: 1.3, fit: "shrink" });
  s.addText(spec.title, { x: 0.72, y: 2.5, w: 7.7, h: 0.75, margin: 0, fontFace: "Aptos Display", fontSize: 34, bold: true, color: C.white, fit: "shrink" });
  s.addText(spec.subtitle, { x: 0.72, y: 3.55, w: 5.5, h: 0.45, margin: 0, fontSize: 22, color: "D8E8EC", fit: "shrink" });
  s.addText("AeroCommand by Maker Skills", { x: 0.72, y: 6.55, w: 4.2, h: 0.25, margin: 0, fontSize: 10.5, color: "B5C8D0", fit: "shrink" });
}

const renderers = { cover, intro, problem, solution, features, target, comparison, business, marketing, demo, conclusion, qa };
slides.forEach((spec, idx) => {
  const s = pptx.addSlide();
  renderers[spec.kind](s, spec, idx + 1);
});

function esc(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function svgText(str, x, y, size, color, weight = 400, width = 900) {
  const words = String(str).split(/\s+/);
  const lines = [];
  let line = "";
  const maxChars = Math.max(10, Math.floor(width / (size * 0.52)));
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > maxChars && line) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  if (line) lines.push(line);
  return lines.map((l, i) => `<text x="${x}" y="${y + i * size * 1.18}" fill="#${color}" font-family="Aptos, Arial" font-size="${size}" font-weight="${weight}">${esc(l)}</text>`).join("");
}

function simplePreview(spec, i) {
  const dark = spec.kind === "cover" || spec.kind === "conclusion" || spec.kind === "qa";
  const bg = dark ? C.deep : spec.kind === "problem" ? "FFF8F3" : spec.kind === "marketing" ? "FFFDF7" : spec.kind === "features" ? "F8FBF6" : C.cloud;
  let body = `<rect width="1920" height="1080" fill="#${bg}"/>`;
  if (dark) {
    body += `<circle cx="1510" cy="130" r="430" fill="#${C.teal}" opacity=".42"/>`;
    body += `<path d="M1120 660 L1710 310 L1770 390 L1180 740 Z" fill="#${C.mint}" opacity=".56"/>`;
  } else {
    body += `<rect x="0" y="940" width="1920" height="44" fill="#${spec.kind === "problem" ? C.coral : C.teal}" opacity=".12"/>`;
  }
  body += svgText((spec.kicker || "Maker Skills").toUpperCase(), 104, 112, 20, dark ? C.lime : C.teal, 700, 680);
  body += svgText(spec.title, 104, spec.kind === "cover" || spec.kind === "qa" ? 350 : 225, spec.kind === "cover" ? 82 : spec.kind === "qa" ? 62 : 54, dark ? C.white : C.ink, 800, spec.kind === "cover" ? 980 : 1430);
  if (spec.subtitle) body += svgText(spec.subtitle, 106, spec.kind === "cover" ? 505 : 515, spec.kind === "cover" ? 36 : 36, dark ? "D8E8EC" : C.muted, 400, 760);
  const items = spec.bullets || spec.problems || spec.features || spec.segments || spec.channels || spec.summary || spec.plans || [];
  if (items.length && spec.kind !== "comparison" && spec.kind !== "demo") {
    items.slice(0, 5).forEach((item, idx) => {
      const text = Array.isArray(item) ? `${item[0]}: ${item[1]}` : item;
      body += `<circle cx="135" cy="${420 + idx * 82}" r="8" fill="#${[C.mint, C.teal, C.coral, C.yellow][idx % 4]}"/>`;
      body += svgText(text, 165, 428 + idx * 82, 25, dark ? "D8E8EC" : C.ink, idx < 3 ? 600 : 400, 1300);
    });
  }
  if (spec.kind === "comparison") {
    spec.rows.forEach((r, ridx) => r.forEach((cell, cidx) => {
      const x = 104 + cidx * 410;
      const y = 310 + ridx * 86;
      body += `<rect x="${x}" y="${y}" width="390" height="78" fill="${ridx === 0 ? "#" + (cidx === 3 ? C.teal : C.navy) : cidx === 3 ? "#E9F7F3" : "#FFFFFF"}" stroke="#${C.line}"/>`;
      body += svgText(cell, x + 18, y + 48, 19, ridx === 0 ? C.white : cidx === 3 ? C.teal : C.ink, ridx === 0 || cidx === 3 ? 700 : 400, 350);
    }));
  }
  if (spec.kind === "demo") {
    body += `<rect x="120" y="275" width="760" height="420" fill="#FFFFFF" stroke="#${C.line}"/><rect x="1040" y="275" width="760" height="420" fill="#FFFFFF" stroke="#${C.line}"/>`;
    body += `<image href="${assetData.screen1}" x="120" y="275" width="760" height="420" preserveAspectRatio="xMidYMid slice"/>`;
    body += `<image href="${assetData.screen2}" x="1040" y="275" width="760" height="420" preserveAspectRatio="xMidYMid slice"/>`;
    body += svgText("Operations dashboard", 260, 770, 25, C.ink, 700, 480);
    body += svgText("Smart farming product page", 1175, 770, 25, C.ink, 700, 520);
  }
  body += svgText("Maker Skills | AeroCommand", 104, 1016, 16, dark ? "B5C8D0" : C.muted, 400, 520);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">${body}</svg>`;
}

async function main() {
  const pptxPath = path.join(outputDir, "MakerSkills_AeroCommand_Farmer_Focused_Commercial_Presentation_v2.pptx");
  await pptx.writeFile({ fileName: pptxPath });
  const previewPaths = [];
  for (let i = 0; i < slides.length; i += 1) {
    const svg = simplePreview(slides[i], i + 1);
    const pngPath = path.join(previewDir, `slide-${String(i + 1).padStart(2, "0")}.png`);
    await sharp(Buffer.from(svg)).png().toFile(pngPath);
    previewPaths.push(pngPath);
  }
  const thumbs = await Promise.all(previewPaths.map((p) => sharp(p).resize(320, 180).toBuffer()));
  const montageRows = Math.ceil(previewPaths.length / 4);
  const montage = sharp({
    create: {
      width: 1280,
      height: montageRows * 180,
      channels: 4,
      background: "#F6FAFB",
    },
  });
  await montage.composite(thumbs.map((input, idx) => ({
    input,
    left: (idx % 4) * 320,
    top: Math.floor(idx / 4) * 180,
  }))).png().toFile(path.join(scratchDir, "preview-montage.png"));
  fs.writeFileSync(path.join(scratchDir, "deck-build-report.json"), JSON.stringify({ pptxPath, previewPaths, slideCount: slides.length }, null, 2));
  console.log(JSON.stringify({ pptxPath, slideCount: slides.length, previewDir, montage: path.join(scratchDir, "preview-montage.png") }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
