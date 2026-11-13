/* Apply the saved surface before the first paint. The renderer stores only
   this display preference; account data never enters localStorage. */
(function () {
  var keys = ["system", "white", "paper", "mist", "apricot", "dark"];
  var theme = "system";
  try {
    var saved = window.localStorage.getItem("bilioshi.theme");
    if (keys.indexOf(saved) >= 0) theme = saved;
  } catch (error) {}
  var root = document.documentElement;
  root.dataset.theme = theme;
  var meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) {
    meta.content = theme === "dark" ? "dark" : theme === "system" ? "light dark" : "light";
  }
})();
