// Filters for the HTML report. Without JavaScript the full report is shown.
(function () {
  var form = document.getElementById("filters");
  if (!form) return;
  var rule = document.getElementById("filter-rule");
  var file = document.getElementById("filter-file");
  var status = document.getElementById("filter-status");
  var total = Number(status.getAttribute("data-total"));
  form.hidden = false;

  function apply() {
    var shown = 0;
    document.querySelectorAll("section.file").forEach(function (section) {
      var fileMatches = !file.value || section.id === file.value;
      var visible = 0;
      section.querySelectorAll("tr[data-rule]").forEach(function (row) {
        var match = fileMatches && (!rule.value || row.getAttribute("data-rule") === rule.value);
        row.hidden = !match;
        if (match) visible += 1;
      });
      section.hidden = visible === 0;
      shown += visible;
    });
    if (shown === total) {
      status.textContent = "";
    } else if (shown === 0) {
      status.textContent = "No problems match these filters.";
    } else {
      status.textContent = "Showing " + shown + " of " + total + " problems";
    }
  }

  rule.addEventListener("change", apply);
  file.addEventListener("change", apply);
  form.addEventListener("reset", function () {
    setTimeout(apply, 0);
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });
})();
