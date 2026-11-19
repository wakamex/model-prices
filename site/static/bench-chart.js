// Benchmark charts: score against a chosen x axis (cost in API dollars, cost in plan dollars,
// or output tokens where a benchmark gives them), on a log or linear scale. Each model's effort
// levels are joined by a line, marked by harness and colored by lab, and named at its best score.

const EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max", ""];
const AXES = {
  api: { label: "Cost in API dollars", money: true },
  plan: { label: "Cost in plan dollars", money: true },
  tokens: { label: "Output tokens", money: false },
};
const SVG = "http://www.w3.org/2000/svg";

const element = (name, attributes = {}, text) => {
  const node = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
};

// A marker per harness, centered on (x, y).
function marker(shape, x, y, color) {
  const r = 5;
  const points = (list) => element("polygon", { points: list.map(([dx, dy]) => `${x + dx},${y + dy}`).join(" "), fill: color });
  switch (shape) {
    case "triangle": return points([[0, -r - 1], [r + 1, r], [-r - 1, r]]);
    case "square": return element("rect", { x: x - r + 0.5, y: y - r + 0.5, width: 2 * r - 1, height: 2 * r - 1, fill: color });
    case "diamond": return points([[0, -r - 1], [r + 1, 0], [0, r + 1], [-r - 1, 0]]);
    case "star": return points(Array.from({ length: 10 }, (_, i) => {
      const angle = Math.PI / 5 * i - Math.PI / 2, length = i % 2 ? r * 0.45 : r + 1.5;
      return [Math.cos(angle) * length, Math.sin(angle) * length];
    }));
    default: return element("circle", { cx: x, cy: y, r, fill: color });
  }
}

const money = (value) => "$" + (value >= 1 ? value.toLocaleString("en-US", { maximumFractionDigits: 0 })
  : value.toLocaleString("en-US", { maximumSignificantDigits: 1 }));
const exact = (value) => "$" + value.toLocaleString("en-US", { maximumSignificantDigits: 3 });
const count = (value) => value >= 1000 ? `${Math.round(value / 1000)}K` : `${value}`;

function ticks(low, high, log) {
  if (log) {
    const found = [];
    for (let power = Math.floor(Math.log10(low)); power <= Math.ceil(Math.log10(high)); power++) {
      const tick = 10 ** power;
      if (tick >= low && tick <= high) found.push(tick);
    }
    return found;
  }
  const step = 10 ** Math.floor(Math.log10((high - low) / 4));
  const size = [1, 2, 5, 10].map((m) => m * step).find((s) => (high - low) / s <= 6);
  const found = [];
  for (let tick = Math.ceil(low / size) * size; tick <= high; tick += size) found.push(tick);
  return found;
}

function draw(chart) {
  const { results, harnesses, axis, log } = chart;
  const width = 1160, height = 680, left = 52, right = 40, top = 20, bottom = 48;
  const shown = results.filter((r) => r[axis] != null && r[axis] > 0);
  const svg = element("svg", { viewBox: `0 0 ${width} ${height}`, class: "bench-chart", role: "img",
    "aria-label": `${chart.name}: score against ${AXES[axis].label.toLowerCase()}` });
  if (!shown.length) return svg;
  const values = shown.map((r) => r[axis]);
  let low = Math.min(...values), high = Math.max(...values);
  if (log) { low = 10 ** (Math.log10(low) - 0.1); high = 10 ** (Math.log10(high) + 0.1); }
  else { const pad = (high - low) * 0.05 || high * 0.1; low = Math.max(0, low - pad); high += pad; }
  const scores = shown.map((r) => r.score);
  const floor = Math.max(0, Math.floor(Math.min(...scores) / 10) * 10), ceiling = Math.ceil((Math.max(...scores) + 2) / 10) * 10;
  const x = (value) => left + (log ? Math.log10(value / low) / Math.log10(high / low) : (value - low) / (high - low)) * (width - left - right);
  const y = (score) => top + (ceiling - score) / (ceiling - floor) * (height - top - bottom);
  for (const tick of ticks(low, high, log)) {
    svg.append(element("line", { x1: x(tick), x2: x(tick), y1: top, y2: height - bottom, class: "bench-grid" }),
      element("text", { x: x(tick), y: height - bottom + 20, class: "bench-tick", "text-anchor": "middle" },
        AXES[axis].money ? money(tick) : count(tick)));
  }
  for (let score = floor; score <= ceiling; score += 10) {
    svg.append(element("line", { x1: left, x2: width - right, y1: y(score), y2: y(score), class: "bench-grid" }),
      element("text", { x: left - 6, y: y(score) + 4, class: "bench-tick", "text-anchor": "end" }, score));
  }
  const models = Map.groupBy(shown, (r) => r.model);
  const labels = [];
  for (const [model, points] of models) {
    points.sort((a, b) => EFFORTS.indexOf(a.effort) - EFFORTS.indexOf(b.effort));
    const color = points[0].color;
    if (points.length > 1) {
      svg.append(element("polyline", { points: points.map((r) => `${x(r[axis])},${y(r.score)}`).join(" "),
        stroke: color, class: "bench-link" }));
    }
    for (const r of points) {
      const mark = marker(harnesses[r.harness] || "circle", x(r[axis]), y(r.score), color);
      mark.append(element("title", {}, `${model} ${r.effort}`.trim() + `: ${r.score}; ` +
        `${exact(r.api)} in API dollars` + (r.plan ? `, ${exact(r.plan)} in plan dollars` : "") +
        (r.tokens ? `, ${r.tokens.toLocaleString("en-US")} output tokens` : "")));
      svg.append(mark);
    }
    const best = points.reduce((a, b) => (b.score > a.score ? b : a));
    labels.push({ model, color, x: x(best[axis]), y: y(best.score) });
  }
  // Each model's name sits beside its best point, moved down past names already placed.
  const placed = [];
  for (const label of labels.sort((a, b) => a.y - b.y)) {
    const size = 7.4 * label.model.length + 10;
    let lx = label.x + 9, ly = label.y - 9;
    if (lx + size > width - right) lx = label.x - 8 - size;
    while (placed.some((p) => lx < p.x + p.w && lx + size > p.x && Math.abs(ly - p.y) < 19)) ly += 19;
    placed.push({ x: lx, y: ly, w: size });
    svg.append(element("rect", { x: lx, y: ly, width: size, height: 18, rx: 2, fill: label.color }),
      element("text", { x: lx + 5, y: ly + 13, class: "bench-tag" }, label.model));
  }
  svg.append(element("text", { x: (left + width - right) / 2, y: height - 6, class: "bench-axis", "text-anchor": "middle" },
    AXES[axis].label + (log ? ", log scale" : "")));
  return svg;
}

// The plan each lab's results are priced on, and each plan's discount: the API dollars a plan
// dollar buys on the lab's main measured pool, which a reader may change. A result's plan cost is
// its API cost over its own pool's measured discount, scaled by the chosen plan's discount
// against the measured plan's.
const panel = document.querySelector(".bench-plans");
const labs = panel ? JSON.parse(panel.querySelector("script").textContent) : [];
const chosen = Object.fromEntries(labs.map((lab) => [lab.lab, lab.measured]));
const renders = [];
const SOURCES = { measured: "measured", stated: "from the usage the plan's name states",
  assumed: "assumed equal to the measured plan's", set: "you set" };

function planCost(r) {
  const lab = labs.find((item) => item.lab === r.lab);
  if (!lab) return r.plan;
  const plan = lab.plans.find((item) => item.id === chosen[r.lab]);
  const own = r.rate * 434.8 / lab.measured_price;
  return r.api / (own * plan.discount / lab.measured_discount);
}

if (panel) {
  const rows = labs.map((lab) => {
    const row = document.createElement("div");
    row.className = "bench-plan";
    const select = document.createElement("select");
    select.replaceChildren(...lab.plans.map((plan) => new Option(
      `${plan.name}, $${plan.price}${plan.id === lab.measured ? " (measured)" : ""}`, plan.id, false, plan.id === lab.measured)));
    const discount = Object.assign(document.createElement("input"), { type: "number", min: "0.01", step: "0.1" });
    const note = document.createElement("span");
    note.className = "bench-plan-note";
    const show = () => {
      const plan = lab.plans.find((item) => item.id === select.value);
      discount.value = plan.discount;
      note.textContent = `${SOURCES[plan.source]}; pool: ${lab.pool}`;
    };
    select.addEventListener("change", () => { chosen[lab.lab] = select.value; show(); renders.forEach((render) => render()); });
    discount.addEventListener("input", () => {
      const value = Number(discount.value);
      if (value > 0) {
        const plan = lab.plans.find((item) => item.id === select.value);
        plan.discount = value;
        plan.source = "set";
        note.textContent = `${SOURCES.set}; pool: ${lab.pool}`;
        renders.forEach((render) => render());
      }
    });
    const label = document.createElement("label");
    label.append(`${lab.name} `, select);
    const value = document.createElement("label");
    value.append("API $ per plan $ ", discount);
    row.append(label, value, note);
    show();
    return row;
  });
  panel.replaceChildren(...rows);
}

for (const container of document.querySelectorAll(".bench")) {
  const chart = { ...JSON.parse(container.querySelector("script").textContent), axis: "plan", log: true };
  const axes = Object.keys(AXES).filter((axis) => chart.results.some((r) => r[axis] != null));
  const head = document.createElement("div");
  head.className = "bench-head";
  const select = document.createElement("select");
  select.replaceChildren(...axes.map((axis) => new Option(AXES[axis].label, axis, false, axis === chart.axis)));
  const scale = document.createElement("span");
  scale.className = "bench-scale";
  const buttons = ["Log", "Linear"].map((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = name;
    button.addEventListener("click", () => { chart.log = name === "Log"; render(); });
    return button;
  });
  scale.append(...buttons);
  head.append(`${chart.name}: score vs `, select, scale);
  const legend = document.createElement("div");
  legend.className = "bench-legend";
  legend.textContent = "Marker by harness: " + Object.entries(chart.harnesses)
    .map(([harness, shape]) => `${{ triangle: "▲", square: "■", diamond: "◆", star: "★" }[shape] || "●"} ${harness}`).join("   ");
  const body = document.createElement("div");
  container.replaceChildren(head, body, legend);
  const render = () => {
    for (const r of chart.results) r.plan = planCost(r);
    buttons.forEach((button) => button.classList.toggle("active", (button.textContent === "Log") === chart.log));
    body.replaceChildren(draw(chart));
  };
  renders.push(render);
  select.addEventListener("change", () => { chart.axis = select.value; render(); });
  render();
}
