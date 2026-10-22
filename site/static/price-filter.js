// Filters the price table by the text typed into the filter box. Punctuation is ignored, so
// "sonnet 5.5" finds claude-sonnet-5-5.
const filter = document.getElementById("price-filter");
const rows = [...document.querySelectorAll(".prose table tbody tr")];
const plain = (text) => text.toLowerCase().replace(/[-._/\s]+/g, "");
filter?.addEventListener("input", () => {
  const terms = filter.value.split(/\s+/).map(plain).filter(Boolean);
  for (const row of rows) {
    const text = plain(row.textContent);
    row.hidden = !terms.every((term) => text.includes(term));
  }
});
