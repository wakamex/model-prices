// The calculator form: prices one request with model-prices.js on the published snapshot.
import { rates, breakdown, period } from "./model-prices.js";

const base = new URL(".", import.meta.url);
const [snapshot, models] = await Promise.all(
  ["snapshot.json", "calculator-models.json"].map((file) => fetch(new URL(file, base)).then((r) => r.json())));
const field = (id) => document.getElementById(id);
const byProvider = Object.groupBy(models, (entry) => entry.provider);
const params = new URLSearchParams(location.search);

const fill = (select, values, chosen) => {
  select.replaceChildren(...values.map(([value, label]) => new Option(label, value, false, value === chosen)));
};
fill(field("provider"),
  Object.entries(byProvider).map(([provider, listed]) => [provider, listed[0].provider_name])
    .sort((a, b) => a[1].localeCompare(b[1])),
  params.get("provider") || "anthropic");

const updateModels = () => {
  const listed = byProvider[field("provider").value] || [];
  fill(field("model"), listed.map((entry) => [entry.model, entry.model]), params.get("model"));
  updateModes();
};
const updateModes = () => {
  const entry = models.find((m) => m.provider === field("provider").value && m.model === field("model").value);
  const modes = entry?.modes || ["standard"];
  fill(field("mode"), modes.map((mode) => [mode === "standard" ? "" : mode, mode]), "");
  field("mode").closest("label").hidden = modes.length < 2;
};
field("at").value = new Date().toISOString().slice(0, 19);

const money = (value) => `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 8 })}`;
const rate = (value) => (value === undefined || value === null ? "input price" : money(value));

function render() {
  const at = `${field("at").value}${field("at").value.length === 16 ? ":00" : ""}Z`;
  const found = rates(snapshot, field("provider").value, field("model").value, at, field("mode").value || null);
  const result = field("result");
  if (found === null) {
    result.textContent = "No price is recorded for this model and mode at that time.";
    return;
  }
  // Longer-lived cache writes have their own price only where the provider sells them.
  const longerLived = found.cache_write_1h_multiple !== undefined && found.cache_write_1h_multiple !== null;
  field("cache_write_1h").closest("label").hidden = !longerLived;
  if (!longerLived) field("cache_write_1h").value = 0;
  const tokens = Object.fromEntries(["input", "output", "cache_read", "cache_write", "cache_write_1h"]
    .map((id) => [id, Math.max(0, Math.trunc(Number(field(id).value) || 0))]));
  const parts = breakdown(found, tokens);
  const rows = [["Input", "input"], ["Output", "output"], ["Cache reads", "cache_read"],
    ["Cache writes", "cache_write"], ...(longerLived ? [["Longer-lived cache writes", "cache_write_1h"]] : [])]
    .map(([label, key]) => `<tr><td>${label}</td><td class="number">${tokens[key].toLocaleString("en-US")}</td><td class="number">${money(parts[key])}</td></tr>`)
    .join("");
  const notes = [
    `Rates from ${found.valid_from.slice(0, 10)} (${found.valid_from_basis}), <a href="${found.source}">source</a>.`,
    `Per million tokens: input ${money(found.input)}, output ${money(found.output)}, cached input ${rate(found.cache_read)}, cache write ${rate(found.cache_write)}.`,
  ];
  if (parts.tier_above !== null) notes.push(`The prompt exceeds ${parts.tier_above.toLocaleString("en-US")} tokens, so that tier's prices apply.`);
  let when = "";
  if (found.period) {
    const [, factor] = period(snapshot, field("provider").value, Date.parse(at), field("model").value);
    const name = found.period.replace("_", "-");
    when = factor === 1 ? `, at ${name} rates` : `, at ${name} rates: ${factor} times the listed prices`;
  }
  result.innerHTML = `<p class="total">${money(parts.total)}${when}</p>
    <table><thead><tr><th>Tokens</th><th>Count</th><th>Cost</th></tr></thead><tbody>${rows}</tbody></table>
    <p>${notes.join(" ")}</p>`;
}

field("provider").addEventListener("change", () => { params.delete("model"); updateModels(); render(); });
field("model").addEventListener("change", () => { updateModes(); render(); });
field("calculator").addEventListener("input", render);
updateModels();
render();
