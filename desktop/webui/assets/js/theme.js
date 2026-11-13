/* Apply the saved surface before the first paint. The renderer stores only
   this display preference; account data never enters localStorage. */
(function () {
  var keys = ["system", "white", "paper", "mist", "dark"];
  var dayKeys = ["white", "paper", "mist"];
  var normalize = function (value, allowed, fallback) {
    var mapped = value === "apricot" ? "paper" : value;
    return allowed.indexOf(mapped) >= 0 ? mapped : fallback;
  };
  var theme = "system";
  var dayTheme = "white";
  try {
    theme = normalize(window.localStorage.getItem("bilioshi.theme"), keys, "system");
    dayTheme = normalize(window.localStorage.getItem("bilioshi.dayTheme"), dayKeys, "white");
  } catch (error) {}
  var root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.dayTheme = dayTheme;
  var meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) {
    meta.content = theme === "dark" ? "dark" : theme === "system" ? "light dark" : "light";
  }
})();
