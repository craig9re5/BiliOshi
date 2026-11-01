/* Colour study controls. The app below is the production renderer with a
   synthetic bridge; this file only switches surface tokens and pages. */

const THEMES = {
  white: {
    number: "01",
    name: "纸白 / Soft White",
    short: "纸白",
    tagline: "中性安静 · Claude 式白",
    description: "最接近 Claude 的暖中性白：主画布几乎是纸面，侧栏只比卡片深一点点。安静、克制，不与内容抢注意力。",
    note: "推荐作为默认主题。它最接近 Claude Desktop 的阅读型表面，也最适合这个每天只被短暂打开一次、但会一直待在后台的应用。",
    tokens: {
      paper: "#fcfcfb",
      surface: "#ffffff",
      sunk: "#f5f5f2",
      hover: "#efefec",
      ink: "#1f1f1d",
      ink2: "rgba(31,31,29,0.68)",
      ink3: "rgba(31,31,29,0.64)",
      line: "rgba(28,28,25,0.08)",
      lineStrong: "rgba(28,28,25,0.14)",
      accent: "#2d6763",
      accentSoft: "#e8f1ee",
      accentLine: "#cfe2dc",
      live: "#1f8a5f",
      liveSoft: "#e9f6ef",
      warn: "#8a5a12",
      warnSoft: "#fdf3e2",
      danger: "#a4432f",
      dangerSoft: "#fbede9"
    }
  },
  paper: {
    number: "02",
    name: "暖纸白 / Quiet Paper",
    short: "暖纸白",
    tagline: "安静自然 · 温和纸感",
    description: "给最常用的界面一层轻微暖意。纸白工作区与白色卡片之间只有很小的明度差，耐看、不打扰。",
    note: "如果你觉得 Claude 白偏冷静，这套更柔和：背景比默认方案多一点米色，但仍在日用可接受的范围内。",
    tokens: {
      paper: "#f6f3ec",
      surface: "#fffdf9",
      sunk: "#efece4",
      hover: "#eae6dd",
      ink: "#26241f",
      ink2: "rgba(38,36,31,0.70)",
      ink3: "rgba(38,36,31,0.66)",
      line: "rgba(45,38,27,0.09)",
      lineStrong: "rgba(45,38,27,0.16)",
      accent: "#2d6763",
      accentSoft: "#e6efeb",
      accentLine: "#c9ddd5",
      live: "#1f8a5f",
      liveSoft: "#e7f4ec",
      warn: "#8a5a12",
      warnSoft: "#fbf1df",
      danger: "#a4432f",
      dangerSoft: "#faeae5"
    }
  },
  mist: {
    number: "03",
    name: "雾青灰 / Mist",
    short: "雾青灰",
    tagline: "清爽克制 · 品牌色更统一",
    description: "冷调非常轻，更像雨后玻璃。青灰中性色与深青主色同源，界面显得干净、利落，又不会变成冷冰冰的仪表盘。",
    note: "适合希望界面更现代、更“工具感”一些的方向；深青按钮在雾青底上尤其完整。",
    tokens: {
      paper: "#f2f6f5",
      surface: "#fbfdfc",
      sunk: "#e9f0ee",
      hover: "#e3ece9",
      ink: "#1e2a28",
      ink2: "rgba(30,42,40,0.70)",
      ink3: "rgba(30,42,40,0.66)",
      line: "rgba(27,50,46,0.09)",
      lineStrong: "rgba(27,50,46,0.16)",
      accent: "#2d6763",
      accentSoft: "#deede9",
      accentLine: "#bfdad4",
      live: "#1b865c",
      liveSoft: "#e2f3ea",
      warn: "#87590f",
      warnSoft: "#f8efdd",
      danger: "#a1412e",
      dangerSoft: "#f8e9e4"
    }
  },
  apricot: {
    number: "04",
    name: "暖杏灰 / Apricot",
    short: "暖杏灰",
    tagline: "温和陪伴 · 降低屏幕冷感",
    description: "暖度比纸白更明显，像傍晚的室内光。应用会更像一件安静的小家具，而不是一块工作面板。",
    note: "适合更看重陪伴感、且主要在夜间使用的方向；白天强光下，杏色底会比另外两套更容易被感知。",
    tokens: {
      paper: "#f8f0e5",
      surface: "#fffaf2",
      sunk: "#f2e8da",
      hover: "#ede1d1",
      ink: "#2c261e",
      ink2: "rgba(44,38,30,0.70)",
      ink3: "rgba(44,38,30,0.66)",
      line: "rgba(56,42,24,0.095)",
      lineStrong: "rgba(56,42,24,0.17)",
      accent: "#2d6763",
      accentSoft: "#e7eeea",
      accentLine: "#cadcd5",
      live: "#1f845b",
      liveSoft: "#e8f3e9",
      warn: "#8a5a12",
      warnSoft: "#fbf0dc",
      danger: "#a4432f",
      dangerSoft: "#f8e8e2"
    }
  }
};

const MAPPING = [
  ["窗口画布", "paper", "--paper", "body / .statusbar / .gain-card"],
  ["侧栏与顶栏", "sunk", "--surface-sunk", ".side / .chrome"],
  ["卡片与选中项", "surface", "--surface", ".card / .nav-item[aria-current]"],
  ["输入框与次级按钮", "surface", "--surface", ".input / .btn / .select"],
  ["状态块与药丸", "sunk", "--surface-sunk", ".state-row / .pill / .notice.neutral"],
  ["列表悬停", "hover", "--surface-hover", ".room:hover / .btn:hover"],
  ["主文字", "ink", "--ink", "标题、正文、选中导航"],
  ["次要文字", "ink2", "--ink-2", "房间元信息、说明正文"],
  ["辅助文字", "ink3", "--ink-3", "时间、计数、脚注"],
  ["细分割线", "line", "--line", "卡片边框、行分隔、顶栏"],
  ["控件描边", "lineStrong", "--line-strong", "按钮、输入框、强分隔"],
  ["主操作", "accent", "--accent", "主按钮、开关开、进度条"],
  ["品牌浅底", "accentSoft", "--accent-soft", "聚焦光晕、账号头像占位"],
  ["直播 / 连接正常", "live", "--live", "直播点、已完成任务"],
  ["提醒 / 保护暂停", "warn", "--warn", "警告条、暂停说明"],
  ["危险操作", "danger", "--danger", "退出登录、移除主播"]
];

const PALETTE_KEYS = ["paper", "surface", "sunk", "ink", "accent", "live"];
const TOKEN_LABELS = {
  paper: "工作区纸面", surface: "卡片", sunk: "侧栏 / 嵌套底", hover: "悬停",
  ink: "主文字", ink2: "次要文字", ink3: "辅助文字", line: "细线", lineStrong: "控件描边",
  accent: "品牌深青", accentSoft: "品牌浅底", accentLine: "品牌描边",
  live: "直播绿", liveSoft: "直播浅底", warn: "警告琥珀", warnSoft: "警告浅底",
  danger: "危险红", dangerSoft: "危险浅底"
};

const params = new URLSearchParams(window.location.search);
const embed = params.get("embed") === "1";
let activeTheme = THEMES[params.get("theme")] ? params.get("theme")
  : (THEMES[localStorage.getItem("bilioshi.colorStudy")] ? localStorage.getItem("bilioshi.colorStudy") : "white");
let compareBuilt = false;

if (embed) document.body.classList.add("embed");

const frame = document.getElementById("preview-frame");
const scaleLayer = document.getElementById("preview-scale");

function fitWindow() {
  if (!frame || !scaleLayer) return;
  const stage = frame.closest(".window-stage");
  const horizontal = embed ? document.documentElement.clientWidth : Math.max(0, stage.clientWidth - 36);
  const vertical = embed ? document.documentElement.clientHeight : 760;
  const scale = Math.min(horizontal / 1180, vertical / 760, 1);
  frame.style.width = `${Math.round(1180 * scale)}px`;
  frame.style.height = `${Math.round(760 * scale)}px`;
  scaleLayer.style.transform = `scale(${scale})`;
}

function swatch(value) {
  return `<i style="background:${value}"></i>`;
}

function renderSummary() {
  const theme = THEMES[activeTheme];
  document.getElementById("scheme-number").textContent = theme.number;
  document.getElementById("scheme-name").textContent = theme.name;
  document.getElementById("scheme-description").textContent = theme.description;
  document.getElementById("palette").innerHTML = PALETTE_KEYS.map((key) =>
    `<span class="palette-chip" style="background:${theme.tokens[key]}" data-hex="${theme.tokens[key]}" title="${TOKEN_LABELS[key]} · ${theme.tokens[key]}"></span>`
  ).join("");
}

function renderMapping() {
  const theme = THEMES[activeTheme];
  const cards = ["paper", "surface", "sunk", "hover", "ink", "ink2", "ink3", "line", "lineStrong", "accent", "accentSoft", "live"].map((key) => `
    <div class="token-card">
      <div class="token-color" style="background:${theme.tokens[key]}"></div>
      <div class="token-name">${TOKEN_LABELS[key]}</div>
      <div class="token-hex">${theme.tokens[key]}</div>
    </div>`).join("");
  document.getElementById("token-grid").innerHTML = cards;
  document.getElementById("mapping-body").innerHTML = MAPPING.map(([part, key, variable, targets]) => `
    <tr>
      <td>${part}</td>
      <td><span class="inline-color">${swatch(theme.tokens[key])}<code>${theme.tokens[key]}</code></span></td>
      <td><code>${variable}</code><br>${targets}</td>
    </tr>`).join("");
}

function renderComparisonSelection() {
  document.querySelectorAll(".compare-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.theme === activeTheme);
  });
}

function applyTheme(key, { updateUrl = true } = {}) {
  if (!THEMES[key]) return;
  activeTheme = key;
  frame.dataset.theme = key;
  localStorage.setItem("bilioshi.colorStudy", key);
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    const active = button.dataset.themeChoice === key;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (!embed) {
    renderSummary();
    renderMapping();
    renderComparisonSelection();
    if (updateUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set("theme", key);
      window.history.replaceState(null, "", url);
    }
  }
}

function selectPage(key) {
  const labels = { monitor: "直播总览", automation: "挂机设置", account: "账号" };
  const button = document.querySelector(`#preview-frame button[aria-label="${labels[key]}"]`);
  if (button) button.click();
  document.querySelectorAll("[data-page-choice]").forEach((item) => {
    item.classList.toggle("active", item.dataset.pageChoice === key);
  });
}

function syncPageTabs() {
  const title = document.querySelector("#preview-frame .chrome-title")?.textContent?.trim();
  const key = { "直播总览": "monitor", "挂机设置": "automation", "账号": "account" }[title];
  if (!key) return;
  document.querySelectorAll("[data-page-choice]").forEach((item) => {
    item.classList.toggle("active", item.dataset.pageChoice === key);
  });
}

function buildComparison() {
  if (compareBuilt) return;
  const comparison = document.getElementById("comparison");
  comparison.innerHTML = Object.entries(THEMES).map(([key, theme]) => {
    const url = new URL("Color Study.html", window.location.href);
    url.searchParams.set("embed", "1");
    url.searchParams.set("theme", key);
    return `<article class="compare-card" data-theme="${key}">
      <div class="compare-frame"><iframe src="${url}" title="${theme.short}预览"></iframe></div>
      <div class="compare-label"><strong>${theme.short}</strong><span>${theme.tagline.split(" · ")[0]}</span><button class="compare-pick" data-pick="${key}">查看</button></div>
    </article>`;
  }).join("");
  compareBuilt = true;
  comparison.querySelectorAll("[data-pick]").forEach((button) => {
    button.addEventListener("click", () => {
      applyTheme(button.dataset.pick);
      comparison.hidden = true;
      document.getElementById("compare-toggle").setAttribute("aria-pressed", "false");
      frame.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
  renderComparisonSelection();
}

function setupControls() {
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeChoice));
  });
  document.querySelectorAll("[data-page-choice]").forEach((button) => {
    button.addEventListener("click", () => selectPage(button.dataset.pageChoice));
  });

  const comparison = document.getElementById("comparison");
  document.getElementById("compare-toggle").addEventListener("click", (event) => {
    buildComparison();
    comparison.hidden = !comparison.hidden;
    event.currentTarget.setAttribute("aria-pressed", String(!comparison.hidden));
    if (!comparison.hidden) comparison.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const mapping = document.getElementById("mapping");
  document.getElementById("spec-toggle").addEventListener("click", (event) => {
    mapping.hidden = !mapping.hidden;
    event.currentTarget.setAttribute("aria-expanded", String(!mapping.hidden));
    if (!mapping.hidden) mapping.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  new MutationObserver(syncPageTabs).observe(document.getElementById("root"), {
    subtree: true, childList: true, characterData: true
  });
  window.addEventListener("resize", fitWindow);
}

applyTheme(activeTheme, { updateUrl: false });
if (!embed) {
  renderSummary();
  renderMapping();
  setupControls();
}
fitWindow();
window.addEventListener("load", () => { fitWindow(); syncPageTabs(); });
if (embed) {
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
}
