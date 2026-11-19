// The Plans page's converter: an API cost per task in plan dollars and tasks a week, from each
// row's API dollars per weekly point and plan dollars per point.
const cost = document.getElementById("task-cost");
const show = () => {
  const value = Math.max(0, Number(cost.value) || 0);
  for (const cell of document.querySelectorAll(".plan-task")) {
    const dollars = value / Number(cell.dataset.rate) * Number(cell.dataset.point);
    cell.textContent = value ? "$" + dollars.toFixed(3) : "";
  }
  for (const cell of document.querySelectorAll(".plan-tasks")) {
    cell.textContent = value ? Math.floor(100 * Number(cell.dataset.rate) / value).toLocaleString("en-US") : "";
  }
};
cost.addEventListener("input", show);
show();
