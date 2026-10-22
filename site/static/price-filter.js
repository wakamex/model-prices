// Filters the price table by the text typed into the filter box.
const filter = document.getElementById("price-filter");
const rows = [...document.querySelectorAll(".prose table tbody tr")];
filter?.addEventListener("input", () => {
  const terms = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
  for (const row of rows) {
    const text = row.textContent.toLowerCase();
    row.hidden = !terms.every((term) => text.includes(term));
  }
});
