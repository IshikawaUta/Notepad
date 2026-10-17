window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    enableMenu: false,
    enableEnrichment: false,
    enableAssistiveMml: false,
    skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"],
    ignoreHtmlClass: "no-mathjax"
  },
  chtml: {
    displayAlign: "center",
    scale: 1
  }
};
