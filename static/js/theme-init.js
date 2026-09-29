(function () {
  try {
    var m = localStorage.getItem("catatan-theme") || "auto";
    if (m !== "light" && m !== "dark" && m !== "auto") m = "auto";
    var root = document.documentElement;
    root.setAttribute("data-theme", m);
    if (m === "auto") root.removeAttribute("data-user-theme");
    else root.setAttribute("data-user-theme", m);
    var dark =
      m === "dark" ||
      (m === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.classList.toggle("dark", dark);
  } catch (e) {}
})();
