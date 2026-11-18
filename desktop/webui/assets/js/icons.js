/* BiliOshi JSX {"code_sha256":"e23bd79054b715b81aef0487e16574bb568c111cc4d7d0a97a11f7a56d560b56","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"icons.jsx","source_sha256":"bb15a1171fd97b7ca689436787976f98bce593ca256c8d5d379fc2a4ce4b35d3"} */
(function () {
"use strict";
/* Hand-drawn 16px stroke icons — one weight, round caps, currentColor.
   Replaces the emoji glyphs used by the Tk UI so every glyph shares a stroke. */

const Icon = ({
  name,
  size = 15,
  stroke = 1.6,
  className = ""
}) => {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: stroke,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": "true"
  };
  const paths = {
    monitor: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "3",
      y: "4.5",
      width: "18",
      height: "12.5",
      rx: "2.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M8.5 20.5h7M12 17v3.5"
    })),
    trend: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M4 16.5 9.2 11l3.3 3.3L20 7.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M15.2 7.2H20v4.8"
    })),
    sliders: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M4 7h9M17 7h3M4 17h3M11 17h9"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "15",
      cy: "7",
      r: "2.1"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "9",
      cy: "17",
      r: "2.1"
    })),
    user: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "8",
      r: "3.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M4.8 20c.7-3.6 3.6-5.6 7.2-5.6s6.5 2 7.2 5.6"
    })),
    folder: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M3.5 7.2c0-1 .8-1.8 1.8-1.8h3.4l1.8 2.2h8.2c1 0 1.8.8 1.8 1.8v8c0 1-.8 1.8-1.8 1.8H5.3c-1 0-1.8-.8-1.8-1.8V7.2Z"
    })),
    check: /*#__PURE__*/React.createElement("path", {
      d: "M4.5 12.4 9.4 17l10.1-10"
    }),
    refresh: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M20 11.4a8 8 0 1 0-2.1 6.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M20 4.8v6.6h-6.6"
    })),
    pause: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "6.6",
      y: "5",
      width: "3.6",
      height: "14",
      rx: "1.1"
    }), /*#__PURE__*/React.createElement("rect", {
      x: "13.8",
      y: "5",
      width: "3.6",
      height: "14",
      rx: "1.1"
    })),
    play: /*#__PURE__*/React.createElement("path", {
      d: "M7.4 5.2v13.6L19 12 7.4 5.2Z"
    }),
    reconnect: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M4.3 10.2A7.9 7.9 0 0 1 18 8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19.7 13.8A7.9 7.9 0 0 1 6 15.6"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M18.4 4.6v4h-4M5.6 19.4v-4h4"
    })),
    external: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M13.8 4.5H19.5V10"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19.5 4.5 11 13"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19.5 14.6v3.6c0 1-.8 1.8-1.8 1.8H5.3c-1 0-1.8-.8-1.8-1.8V6.3c0-1 .8-1.8 1.8-1.8h3.6"
    })),
    plus: /*#__PURE__*/React.createElement("path", {
      d: "M12 5v14M5 12h14"
    }),
    alert: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 4.6 21 19.4H3L12 4.6Z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 10v4.2M12 17.2v.1"
    })),
    info: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 11v5.2M12 7.9v.1"
    })),
    shield: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 3.6 19 6v5.4c0 4-2.8 7-7 8.9-4.2-1.9-7-4.9-7-8.9V6l7-2.4Z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M9 12.2 11.3 14.5 15.3 10"
    })),
    clock: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 7.4V12l3.2 1.9"
    })),
    qr: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "4",
      y: "4",
      width: "6",
      height: "6",
      rx: "1.2"
    }), /*#__PURE__*/React.createElement("rect", {
      x: "14",
      y: "4",
      width: "6",
      height: "6",
      rx: "1.2"
    }), /*#__PURE__*/React.createElement("rect", {
      x: "4",
      y: "14",
      width: "6",
      height: "6",
      rx: "1.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M14 14h2.6v2.6H14zM18.4 18.4H20V20h-1.6z"
    })),
    bell: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M6.4 10.2a5.6 5.6 0 0 1 11.2 0c0 4 1.4 5.4 1.4 5.4H5s1.4-1.4 1.4-5.4Z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M10 19a2.2 2.2 0 0 0 4 0"
    })),
    power: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 4.6v7"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M7.6 7.2a7 7 0 1 0 8.8 0"
    })),
    chevron: /*#__PURE__*/React.createElement("path", {
      d: "M6.5 9.2 12 14.6l5.5-5.4"
    }),
    circle: /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "8.4"
    }),
    trash: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M4.5 7.2h15"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M9.4 7.2V5.3c0-.7.6-1.3 1.3-1.3h2.6c.7 0 1.3.6 1.3 1.3v1.9"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M6.8 7.2l.8 11.2c.1.9.8 1.6 1.7 1.6h5.4c.9 0 1.6-.7 1.7-1.6l.8-11.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M10.2 11v4.6M13.8 11v4.6"
    })),
    more: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "5",
      cy: "12",
      r: "1"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "1"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "19",
      cy: "12",
      r: "1"
    })),
    medal: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "9",
      r: "5.5"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M8 13.5 6.5 21l5.5-3 5.5 3-1.5-7.5"
    })),
    download: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 4.5v10.5M7.8 11.2 12 15.4l4.2-4.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M4.5 16.8v1.6c0 .9.7 1.6 1.6 1.6h11.8c.9 0 1.6-.7 1.6-1.6v-1.6"
    })),
    copy: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "8.5",
      y: "8.5",
      width: "11",
      height: "11",
      rx: "2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M5.5 15.5H5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5h9a1.5 1.5 0 0 1 1.5 1.5v.5"
    })),
    contrast: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "7.8"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 4.2a7.8 7.8 0 0 1 0 15.6Z",
      fill: "currentColor",
      stroke: "none"
    })),
    search: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "10.8",
      cy: "10.8",
      r: "6.3"
    }), /*#__PURE__*/React.createElement("path", {
      d: "m15.6 15.6 4.4 4.4"
    })),
    close: /*#__PURE__*/React.createElement("path", {
      d: "M6.8 6.8l10.4 10.4M17.2 6.8 6.8 17.2"
    }),
    chat: /*#__PURE__*/React.createElement("path", {
      d: "M5.4 5.8h13.2c1 0 1.9.8 1.9 1.8v7.4c0 1-.9 1.8-1.9 1.8H10.2l-4 2.9v-2.9H5.4c-1 0-1.9-.8-1.9-1.8V7.6c0-1 .9-1.8 1.9-1.8Z"
    }),
    heart: /*#__PURE__*/React.createElement("path", {
      d: "M12 19.5s-6.8-4.2-8.4-8.3c-.9-2.8 1-5.5 3.9-5.5 1.8 0 3.3.9 4.5 2.4 1.2-1.5 2.7-2.4 4.5-2.4 2.9 0 4.8 2.7 3.9 5.5-1.6 4.1-8.4 8.3-8.4 8.3Z"
    }),
    sparkles: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "4",
      y: "5.5",
      width: "16",
      height: "14.5",
      rx: "2.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M8 3.6v3.4M16 3.6v3.4M4 10h16M9.4 14.8l1.8 1.8 3.6-3.6"
    })),
    coin: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 7.8v8.4M9.4 10h5.2"
    })),
    share: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 4.5v10M8.2 8.2 12 4.5l3.8 3.7"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M5 14.5v3.6c0 1 .8 1.9 1.9 1.9h10.2c1 0 1.9-.9 1.9-1.9v-3.6"
    })),
    video: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "3.5",
      y: "5.5",
      width: "17",
      height: "13",
      rx: "2.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M10.2 9.2v5.6L15 12l-4.8-2.8Z"
    }))
  };
  return /*#__PURE__*/React.createElement("svg", common, paths[name] || paths.info);
};
const Pulse = ({
  size = 18,
  className = ""
}) => {
  const rawId = React.useId();
  const maskId = `oshi-${String(rawId).replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 120 120",
    fill: "none",
    className: className,
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("mask", {
    id: maskId,
    maskUnits: "userSpaceOnUse",
    maskContentUnits: "userSpaceOnUse",
    x: "0",
    y: "0",
    width: "120",
    height: "120"
  }, /*#__PURE__*/React.createElement("rect", {
    x: "0",
    y: "0",
    width: "120",
    height: "120",
    fill: "#ffffff"
  }), /*#__PURE__*/React.createElement("g", {
    fill: "none",
    stroke: "#000000",
    strokeWidth: "7.8",
    strokeLinecap: "butt",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("line", {
    x1: "18.5",
    y1: "37",
    x2: "47.5",
    y2: "37"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M 33.3 24 V 82.5 A 7.5 7.5 0 0 1 18.3 82.5 V 77 A 7.5 7.5 0 0 1 22.87 70.09 L 40.54 62.61 A 14 14 0 1 1 45.51 89.49"
  })), /*#__PURE__*/React.createElement("circle", {
    cx: "58.2",
    cy: "35",
    r: "4.8",
    fill: "#000000"
  }))), /*#__PURE__*/React.createElement("rect", {
    x: "9",
    y: "16",
    width: "63",
    height: "88",
    rx: "16",
    fill: "currentColor",
    mask: `url(#${maskId})`
  }), /*#__PURE__*/React.createElement("path", {
    d: "M 87.5 20 V 88.5 A 10 10 0 0 0 106.9 91.92 L 108.78 86.75",
    stroke: "currentColor",
    strokeWidth: "11",
    strokeLinecap: "butt"
  }));
};
Object.assign(window, {
  Icon,
  Pulse
});
})();
