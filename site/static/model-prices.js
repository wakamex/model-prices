// Prices a request from a model-prices snapshot as the Python package's rates() and
// Rates.breakdown() do, with the same floating-point operations in the same order, so the
// results are identical. tests/test_site.py checks this against the package.

const SECOND = 1000;

function parseTime(value) {
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) throw new Error(`not a time: ${value}`);
  return ms;
}

// The compiled rates in effect at `at` (milliseconds), before any time-of-day rule.
function lookup(snapshot, provider, model, at, mode) {
  const timelines = (snapshot.prices[provider] || {})[model] || {};
  if (mode === "thinking" && !("thinking" in timelines)) mode = null;
  const intervals = timelines[mode || "standard"] || [];
  if (intervals.length === 0) return null;
  // The first interval also covers every earlier time.
  let index = 0;
  for (let i = 1; i < intervals.length; i++) {
    if (parseTime(intervals[i].start) <= at) index = i;
  }
  const stored = intervals[index].rates;
  if (stored === null) return null;
  return { ...stored, tiers: stored.tiers || [] };
}

function secondsOfDay(at) {
  const day = new Date(at);
  return day.getUTCHours() * 3600 + day.getUTCMinutes() * 60 + day.getUTCSeconds()
    + day.getUTCMilliseconds() / SECOND;
}

function inWindow(at, [start, end]) {
  const clock = (value) => {
    const [hours, minutes] = value.split(":").map(Number);
    return hours * 3600 + minutes * 60;
  };
  const time = secondsOfDay(at);
  const from = clock(start);
  const until = clock(end);
  return from <= until ? from <= time && time < until : time >= from || time < until;
}

// The time-of-day period at `at` and its multiplier on the recorded rates, or null.
export function period(snapshot, provider, at, model) {
  const schedules = (snapshot.schedules.schedule || []).filter((item) => item.provider === provider);
  const schedule = schedules.find((item) => parseTime(item.valid_from) <= at
    && (item.valid_until === undefined || at < parseTime(item.valid_until)));
  if (!schedule) return null;
  if ("off_peak_hours_utc" in schedule) {
    const factor = schedule.off_peak_multiplier[model || ""];
    if (factor === undefined) return null;
    const offPeak = schedule.off_peak_hours_utc.some((window) => inWindow(at, window));
    return offPeak ? ["off_peak", factor] : ["standard", 1.0];
  }
  let peak = schedule.peak_hours_utc.some((window) => inWindow(at, window));
  const weekday = new Date(at).getUTCDay();
  if (schedule.weekdays_only && (weekday === 0 || weekday === 6)) peak = false;
  const calendar = (snapshot.schedules.holidays || {})[schedule.holidays || ""];
  if (calendar) {
    const local = new Date(at + calendar.utc_offset_hours * 3600 * SECOND).toISOString().slice(0, 10);
    peak = peak && !calendar.dates.includes(local);
  }
  return peak ? ["peak", schedule.peak_multiplier] : ["off_peak", 1.0];
}

function scaled(found, label, factor) {
  const scale = (value) => (value === undefined || value === null ? value : value * factor);
  return {
    ...found,
    period: label,
    input: found.input * factor,
    output: found.output * factor,
    cache_read: scale(found.cache_read),
    cache_write: scale(found.cache_write),
    tiers: found.tiers.map((tier) => ({
      ...tier,
      input: scale(tier.input),
      output: scale(tier.output),
      cache_read: scale(tier.cache_read),
      cache_write: scale(tier.cache_write),
    })),
  };
}

// The rates for a request made at `at` (an ISO time or milliseconds), or null.
export function rates(snapshot, provider, model, at, mode = null) {
  const moment = typeof at === "number" ? at : parseTime(at);
  const found = lookup(snapshot, provider, model, moment, mode);
  if (found === null) return null;
  const current = period(snapshot, provider, moment, model);
  return current ? scaled(found, ...current) : { ...found, period: null };
}

const present = (value) => value !== undefined && value !== null;

// The cost of one request by token type, in USD; input excludes cache reads and writes.
export function breakdown(found, tokens) {
  const input = tokens.input || 0;
  const output = tokens.output || 0;
  const cacheRead = tokens.cache_read || 0;
  const cacheWrite = tokens.cache_write || 0;
  const cacheWrite1h = tokens.cache_write_1h || 0;
  const prompt = input + cacheRead + cacheWrite + cacheWrite1h;
  const current = {
    input: found.input, output: found.output,
    cache_read: found.cache_read, cache_write: found.cache_write,
  };
  let applied = null;
  for (const tier of found.tiers) {
    if (prompt > tier.above) {
      applied = tier.above;
      for (const key of ["input", "output", "cache_read", "cache_write"]) {
        if (present(tier[key])) current[key] = tier[key];
      }
    }
  }
  const inputRate = current.input;
  const cacheReadRate = present(current.cache_read) ? current.cache_read : inputRate;
  const cacheWriteRate = present(current.cache_write) ? current.cache_write : inputRate;
  const cacheWrite1hRate = present(found.cache_write_1h_multiple)
    ? inputRate * found.cache_write_1h_multiple : cacheWriteRate;
  const parts = {
    tier_above: applied,
    input: input * inputRate / 1e6,
    output: output * current.output / 1e6,
    cache_read: cacheRead * cacheReadRate / 1e6,
    cache_write: cacheWrite * cacheWriteRate / 1e6,
    cache_write_1h: cacheWrite1h * cacheWrite1hRate / 1e6,
  };
  parts.total = parts.input + parts.output + parts.cache_read + parts.cache_write + parts.cache_write_1h;
  return parts;
}
