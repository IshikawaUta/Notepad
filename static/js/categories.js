(function () {
  "use strict";
  document.querySelectorAll("[data-edit-cat]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const id = btn.getAttribute("data-edit-cat");
      document.getElementById("edit-cat-form").action = "/admin/kategori/" + id + "/edit";
      document.getElementById("edit-cat-name").value = btn.getAttribute("data-name") || "";
      document.getElementById("edit-cat-desc").value = btn.getAttribute("data-desc") || "";
      document.getElementById("edit-cat-color").value = btn.getAttribute("data-color") || "#6366f1";
      const panel = document.getElementById("edit-cat-panel");
      panel.hidden = false;
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });
})();
