/* Apply the saved surface before the first paint. The renderer stores only
   this display preference; account data never enters localStorage. */
(function () {
  var keys = ["white", "paper", "mist", "apricot"];
  try {
    var saved = window.localStorage.getItem("bilioshi.theme");
    document.documentElement.dataset.theme = keys.indexOf(saved) >= 0 ? saved : "white";
  } catch (error) {
    document.documentElement.dataset.theme = "white";
  }
})();
