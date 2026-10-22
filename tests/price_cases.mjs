// Prices the cases in argv[3] from the snapshot in argv[2] with the site's calculator module
// and prints the results as JSON, for tests/test_site.py.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const [, , snapshotPath, casesPath, modulePath] = process.argv;
const { rates, breakdown } = await import(pathToFileURL(modulePath).href);
const snapshot = JSON.parse(readFileSync(snapshotPath, "utf8"));
const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const results = cases.map(({ provider, model, at, mode, tokens }) => {
  const found = rates(snapshot, provider, model, at, mode);
  return found === null ? null : { period: found.period, ...breakdown(found, tokens) };
});
process.stdout.write(JSON.stringify(results));
