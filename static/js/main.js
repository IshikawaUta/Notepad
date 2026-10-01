(function () {
  "use strict";

  const root = document.documentElement;
  const THEME_KEY = "catatan-theme";
  const THEME_ORDER = ["light", "dark", "auto"];

  function systemPrefersDark() {
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch (_) {
      return false;
    }
  }

  function readSavedTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || "auto";
    } catch (_) {
      return "auto";
    }
  }

  function saveTheme(mode) {
    try {
      localStorage.setItem(THEME_KEY, mode);
    } catch (_) {}
  }

  function isDarkMode(mode) {
    if (mode === "dark") return true;
    if (mode === "light") return false;
    return systemPrefersDark();
  }

  function updateThemeColor(dark) {
    const color = dark ? "#1e1e1e" : "#ffffff";
    document.querySelectorAll('meta[name="theme-color"]').forEach(function (meta) {
      meta.removeAttribute("media");
      meta.setAttribute("content", color);
    });
  }

  function setThemeIcon(dark) {
    document.querySelectorAll("#theme-icon, [data-theme-icon]").forEach(function (icon) {
      icon.className = dark ? "fa-solid fa-sun" : "fa-solid fa-moon";
    });
    document.querySelectorAll("[data-theme-label]").forEach(function (el) {
      const mode = root.getAttribute("data-theme") || "auto";
      const labels = { light: "Terang", dark: "Gelap", auto: "Otomatis" };
      el.textContent = labels[mode] || "Otomatis";
    });
    document.querySelectorAll("#theme-toggle, [data-theme-toggle]").forEach(function (btn) {
      const mode = root.getAttribute("data-theme") || "auto";
      const labels = { light: "Terang", dark: "Gelap", auto: "Otomatis" };
      btn.setAttribute("title", "Tema: " + labels[mode]);
      btn.setAttribute("aria-label", "Tema: " + labels[mode] + " — klik untuk ganti");
    });
  }

  function applyTheme(mode) {
    if (THEME_ORDER.indexOf(mode) === -1) mode = "auto";
    root.setAttribute("data-theme", mode);
    if (mode === "auto") {
      root.removeAttribute("data-user-theme");
    } else {
      root.setAttribute("data-user-theme", mode);
    }
    const dark = isDarkMode(mode);
    root.classList.toggle("dark", dark);
    updateThemeColor(dark);
    setThemeIcon(dark);
    saveTheme(mode);
    document.dispatchEvent(new CustomEvent("themechange", { detail: { mode: mode, dark: dark } }));
  }

  function cycleTheme() {
    const cur = root.getAttribute("data-theme") || readSavedTheme();
    // Selalu langsung ke kebalikan visual saat ini sebagai mode eksplisit.
    // Hindari langkah no-op seperti auto→light saat auto sudah terang (OS light).
    applyTheme(isDarkMode(cur) ? "light" : "dark");
  }

  // Initial theme (also callable from inline head script)
  window.__applyCatatanTheme = applyTheme;
  applyTheme(readSavedTheme());

  document.querySelectorAll("#theme-toggle, [data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", cycleTheme);
  });

  // Sync with OS when in auto mode
  try {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      const mode = root.getAttribute("data-theme") || "auto";
      if (mode === "auto") applyTheme("auto");
    });
  } catch (_) {}

  // ── Public mobile nav ────────────────────────────────────────────
  const navToggle = document.getElementById("nav-toggle");
  const navMobile = document.getElementById("nav-mobile");

  function setNavOpen(open) {
    if (!navToggle || !navMobile) return;
    if (open) {
      navMobile.hidden = false;
      navToggle.setAttribute("aria-expanded", "true");
      navToggle.setAttribute("aria-label", "Tutup menu");
      const icon = navToggle.querySelector("i");
      if (icon) icon.className = "fa-solid fa-xmark";
    } else {
      navMobile.hidden = true;
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Buka menu");
      const icon = navToggle.querySelector("i");
      if (icon) icon.className = "fa-solid fa-bars";
    }
  }

  if (navToggle && navMobile) {
    navToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      setNavOpen(navMobile.hidden);
    });

    // Close when tapping a link inside
    navMobile.addEventListener("click", function (e) {
      const link = e.target.closest("a");
      if (link) setNavOpen(false);
    });

    // Close on outside click
    document.addEventListener("click", function (e) {
      if (navMobile.hidden) return;
      if (navMobile.contains(e.target) || navToggle.contains(e.target)) return;
      setNavOpen(false);
    });

    // Close on Escape
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !navMobile.hidden) {
        setNavOpen(false);
        navToggle.focus();
      }
    });

    // Close when resizing to desktop
    try {
      window.matchMedia("(min-width: 768px)").addEventListener("change", function (mq) {
        if (mq.matches) setNavOpen(false);
      });
    } catch (_) {}
  }

  // ── Admin sidebar ────────────────────────────────────────────────
  const adminMenuBtn = document.getElementById("admin-menu-btn");
  const adminSidebar = document.getElementById("admin-sidebar");
  const sidebarBackdrop = document.getElementById("sidebar-backdrop");

  function setSidebarOpen(open) {
    if (!adminSidebar) return;
    adminSidebar.classList.toggle("open", open);
    if (sidebarBackdrop) {
      sidebarBackdrop.classList.toggle("show", open);
      if (open) sidebarBackdrop.removeAttribute("hidden");
      else sidebarBackdrop.setAttribute("hidden", "");
    }
    if (adminMenuBtn) {
      adminMenuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      adminMenuBtn.setAttribute("aria-label", open ? "Tutup menu" : "Buka menu");
    }
    document.body.style.overflow = open && window.innerWidth < 960 ? "hidden" : "";
  }

  if (adminMenuBtn && adminSidebar) {
    adminMenuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      setSidebarOpen(!adminSidebar.classList.contains("open"));
    });

    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener("click", function () {
        setSidebarOpen(false);
      });
    }

    document.addEventListener("click", function (e) {
      if (!adminSidebar.classList.contains("open")) return;
      if (adminSidebar.contains(e.target) || adminMenuBtn.contains(e.target)) return;
      setSidebarOpen(false);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && adminSidebar.classList.contains("open")) {
        setSidebarOpen(false);
        if (adminMenuBtn) adminMenuBtn.focus();
      }
    });

    // Close after navigating via sidebar link
    adminSidebar.addEventListener("click", function (e) {
      const link = e.target.closest("a");
      if (link && window.innerWidth < 960) setSidebarOpen(false);
    });

    try {
      window.matchMedia("(min-width: 960px)").addEventListener("change", function (mq) {
        if (mq.matches) setSidebarOpen(false);
      });
    } catch (_) {}
  }

  // ── Password visibility ──────────────────────────────────────────
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const id = btn.getAttribute("data-toggle-password");
      const input = document.getElementById(id);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      const icon = btn.querySelector("i");
      if (icon) icon.className = showing ? "fa-solid fa-eye" : "fa-solid fa-eye-slash";
      btn.setAttribute("aria-label", showing ? "Tampilkan password" : "Sembunyikan password");
    });
  });

  // -- Minimal markdown (preview only) --
  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function isSafeUrl(url) {
    const u = String(url || "").trim();
    if (!u) return false;
    const lower = u.toLowerCase();
    if (/^(javascript|vbscript):/.test(lower)) return false;
    if (lower.startsWith("data:")) {
      return /^data:image\/(png|jpe?g|gif|webp|avif|svg\+xml);/i.test(u);
    }
    return true;
  }

  const SAFE_RAW_TAGS =
    "p|div|span|center|figure|figcaption|img|br|hr|strong|em|b|i|u|s|strike|small|sub|sup|code|pre|blockquote|h[1-6]|ul|ol|li|a|table|thead|tbody|tfoot|tr|th|td|kbd|mark|details|summary|abbr";

  function sanitizeRawHtml(html) {
    let t = String(html);
    t = t.replace(/<(script|style|iframe|object|embed|link|meta|base|form)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "");
    t = t.replace(/<(script|style|iframe|object|embed|link|meta|base|form)\b[^>]*\/?>/gi, "");
    t = t.replace(/\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "");
    t = t.replace(/\s+(style|srcdoc|formaction|action|background)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "");
    t = t.replace(/\s+(src|href|xlink:href)\s*=\s*(["'])([\s\S]*?)\2/gi, function (m, attr, q, url) {
      if (!isSafeUrl(url)) return "";
      return " " + attr + "=" + q + url + q;
    });
    t = t.replace(
      /<([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^>]*?)?)\s*(\/?)>/g,
      function (full, tag, attrs, slash) {
        const name = tag.toLowerCase();
        if (!new RegExp("^(" + SAFE_RAW_TAGS + ")$", "i").test(name)) return "";
        const allowed = {
          p: ["align", "class", "id", "dir", "lang", "title"],
          div: ["align", "class", "id", "dir", "lang", "title"],
          center: ["class", "id"],
          img: ["src", "alt", "width", "height", "loading", "decoding", "title", "class", "id"],
          a: ["href", "title", "class", "id", "target", "rel"],
          td: ["colspan", "rowspan", "align", "valign", "class", "id"],
          th: ["colspan", "rowspan", "align", "valign", "scope", "class", "id"]
        };
        const ok = allowed[name] || ["class", "id", "title", "dir", "lang"];
        const kept = [];
        const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))/g;
        let am;
        while ((am = re.exec(attrs || ""))) {
          const key = am[1].toLowerCase();
          if (ok.indexOf(key) === -1) continue;
          const val = am[2] != null ? am[2] : am[3] != null ? am[3] : am[4] || "";
          if ((key === "src" || key === "href") && !isSafeUrl(val)) continue;
          kept.push(key + '="' + String(val).replace(/"/g, "&quot;") + '"');
        }
        if (name === "a" && /\btarget\s*=/i.test(attrs || "")) {
          kept.push('rel="noopener noreferrer"');
        }
        return "<" + name + (kept.length ? " " + kept.join(" ") : "") + (slash ? " /" : "") + ">";
      }
    );
    t = t.replace(/<\/([a-zA-Z][a-zA-Z0-9]*)\s*>/g, function (full, tag) {
      return new RegExp("^(" + SAFE_RAW_TAGS + ")$", "i").test(tag) ? full : "";
    });
    return t;
  }

  function extractSafeHtml(src) {
    const store = [];
    let text = String(src || "");
    text = text.replace(
      /<(p|div|center|figure|figcaption|blockquote|ul|ol|table|thead|tbody|tfoot|details|summary)(\s[^>]*)?>[\s\S]*?<\/\1\s*>/gi,
      function (m) {
        store.push(sanitizeRawHtml(m));
        return "\n" + "\u0000HTML" + (store.length - 1) + "\u0000" + "\n";
      }
    );
    text = text.replace(
      /<\/?(?:img|br|hr|a|strong|em|b|i|u|s|strike|small|sub|sup|code|span|kbd|mark|abbr|h[1-6])\b[^>]*\/?>/gi,
      function (m) {
        store.push(sanitizeRawHtml(m));
        return "\u0000HTML" + (store.length - 1) + "\u0000";
      }
    );
    return { text: text, store: store };
  }

  function inline(s) {
    let t = String(s == null ? "" : s);
    t = t.replace(/`([^`]+)`/g, function (_, c) {
      return "<code>" + c + "</code>";
    });
    t = t.replace(
      /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
      function (_, alt, url, title) {
        if (!isSafeUrl(url)) return "";
        const ti = title ? ' title="' + title + '"' : "";
        return (
          '<img src="' + url + '" alt="' + alt + '"' + ti +
          ' loading="lazy" decoding="async">'
        );
      }
    );
    t = t.replace(
      /\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
      function (_, text, url, title) {
        if (!isSafeUrl(url)) return "";
        const ti = title ? ' title="' + title + '"' : "";
        return '<a href="' + url + '"' + ti + ">" + text + "</a>";
      }
    );
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    t = t.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    t = t.replace(/(^|[^a-zA-Z0-9_])_([^_]+)_(?=[^a-zA-Z0-9_]|$)/g, "$1<em>$2</em>");
    t = t.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    return t;
  }

  function splitTableRow(s) {
    let t = s.trim();
    if (t.charAt(0) === "|") t = t.slice(1);
    if (t.charAt(t.length - 1) === "|") t = t.slice(0, -1);
    const cells = [];
    let cur = "";
    for (let i = 0; i < t.length; i++) {
      const ch = t.charAt(i);
      if (ch === "\\" && t.charAt(i + 1) === "|") { cur += "|"; i++; continue; }
      if (ch === "|") { cells.push(cur.trim()); cur = ""; continue; }
      cur += ch;
    }
    cells.push(cur.trim());
    return cells;
  }

  function isTableSepLine(s) {
    const t = String(s || "").trim();
    if (t.indexOf("-") === -1) return false;
    return /^\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?$/.test(t);
  }

  function isTableRowLine(s) {
    return String(s || "").indexOf("|") !== -1 && !isTableSepLine(s);
  }

  function isTableStart(line, next) {
    if (!next || String(line).indexOf("|") === -1) return false;
    if (!isTableSepLine(next)) return false;
    return splitTableRow(line).length === splitTableRow(next).length;
  }

  function mdToHtml(src) {
    const extracted = extractSafeHtml(src);
    const htmlStore = extracted.store;
    let text = escapeHtml(extracted.text);
    const blocks = [];
    text = text.replace(/```([\s\S]*?)```/g, function (_, raw) {
      let body = raw.replace(/^\n+|\n+$/g, "");
      let lang = "";
      const nl = body.indexOf("\n");
      if (nl !== -1) {
        const first = body.slice(0, nl).trim();
        if (/^[a-zA-Z][\w+#.-]{0,20}$/.test(first) && HL_LANG_NAMES.test(first.toLowerCase())) {
          lang = first.toLowerCase();
          body = body.slice(nl + 1);
        }
      }
      const cls = lang ? ' class="language-' + lang.replace(/[^\w+#.-]/g, "") + '"' : "";
      blocks.push("<pre><code" + cls + ">" + body + "\n</code></pre>");
      return "\u0000BLOCK" + (blocks.length - 1) + "\u0000";
    });

    const lines = text.split("\n");
    const out = [];
    let inUl = false;
    let inOl = false;
    let inBq = false;
    let para = [];

    function closeLists() {
      if (inUl) { out.push("</ul>"); inUl = false; }
      if (inOl) { out.push("</ol>"); inOl = false; }
      if (inBq) { out.push("</blockquote>"); inBq = false; }
    }

    function flushPara() {
      if (para.length) {
        out.push("<p>" + para.map(inline).join("\n") + "</p>");
        para = [];
      }
    }

    function isHtmlPlaceholderLine(line) {
      return /^\u0000HTML\d+\u0000$/.test(line.trim());
    }

    function isBlockLine(line) {
      return (
        /^\u0000BLOCK\d+\u0000$/.test(line.trim()) ||
        isHtmlPlaceholderLine(line) ||
        /^(#{1,6})\s+/.test(line) ||
        /^\s*([-*_])\s*\1\s*\1[\s-]*$/.test(line) ||
        /^\s*[-*+]\s+/.test(line) ||
        /^\s*\d+\.\s+/.test(line) ||
        /^>\s?/.test(line)
      );
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let m;
      if (line.trim() === "") {
        flushPara();
        closeLists();
        continue;
      }
      if (i + 1 < lines.length && isTableStart(line, lines[i + 1])) {
        flushPara();
        closeLists();
        const headCells = splitTableRow(line);
        const aligns = splitTableRow(lines[i + 1]).map(function (c) {
          const l = c.charAt(0) === ":", r = c.charAt(c.length - 1) === ":";
          return l && r ? "center" : r ? "right" : l ? "left" : "";
        });
        let tbl = "<table><thead><tr>";
        for (let c = 0; c < headCells.length; c++) {
          const a = aligns[c] ? ' style="text-align:' + aligns[c] + '"' : "";
          tbl += "<th" + a + ">" + inline(headCells[c]) + "</th>";
        }
        tbl += "</tr></thead>";
        i += 2;
        const bodyRows = [];
        while (i < lines.length && lines[i].trim() !== "" && isTableRowLine(lines[i])) {
          bodyRows.push(splitTableRow(lines[i]));
          i++;
        }
        i--;
        if (bodyRows.length) {
          tbl += "<tbody>";
          for (let r = 0; r < bodyRows.length; r++) {
            tbl += "<tr>";
            for (let c = 0; c < headCells.length; c++) {
              const v = bodyRows[r][c] !== undefined ? bodyRows[r][c] : "";
              const a = aligns[c] ? ' style="text-align:' + aligns[c] + '"' : "";
              tbl += "<td" + a + ">" + inline(v) + "</td>";
            }
            tbl += "</tr>";
          }
          tbl += "</tbody>";
        }
        tbl += "</table>";
        out.push(tbl);
        continue;
      }
      if (isBlockLine(line)) {
        flushPara();
        if (/^\u0000BLOCK\d+\u0000$/.test(line.trim()) || isHtmlPlaceholderLine(line)) {
          closeLists();
          out.push(line.trim());
          continue;
        }
        if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
          closeLists();
          const lv = m[1].length;
          out.push("<h" + lv + ">" + inline(m[2]) + "</h" + lv + ">");
          continue;
        }
        if (/^\s*([-*_])\s*\1\s*\1[\s-]*$/.test(line)) {
          closeLists();
          out.push("<hr>");
          continue;
        }
        if ((m = line.match(/^\s*[-*+]\s+(.*)$/))) {
          if (inOl || inBq) closeLists();
          if (!inUl) { out.push("<ul>"); inUl = true; }
          out.push("<li>" + inline(m[1]) + "</li>");
          continue;
        }
        if ((m = line.match(/^\s*\d+\.\s+(.*)$/))) {
          if (inUl || inBq) closeLists();
          if (!inOl) { out.push("<ol>"); inOl = true; }
          out.push("<li>" + inline(m[1]) + "</li>");
          continue;
        }
        if ((m = line.match(/^>\s?(.*)$/))) {
          if (inUl || inOl) closeLists();
          if (!inBq) { out.push("<blockquote>"); inBq = true; }
          out.push("<p>" + inline(m[1]) + "</p>");
          continue;
        }
      }
      if (inUl || inOl || inBq) {
        flushPara();
        closeLists();
      }
      para.push(line);
    }
    flushPara();
    closeLists();
    let html = out.join("\n");
    html = html.replace(/\u0000BLOCK(\d+)\u0000/g, function (_, i) {
      return blocks[Number(i)] || "";
    });
    html = html.replace(/\u0000HTML(\d+)\u0000/g, function (_, i) {
      return htmlStore[Number(i)] || "";
    });
    return html;
  }

  // -- Syntax highlight (client) + copy button --
  const HL_LANG_NAMES = /^(python|py|js|javascript|ts|typescript|jsx|mjs|bash|sh|shell|zsh|json|css|html|xml|svg|sql|c|cpp|go|rust|java|php|md|markdown|yaml|yml|toml|ini|diff|text|txt)$/;

  const HL_LANG_ALIASES = {
    py: "python", python: "python",
    js: "javascript", javascript: "javascript",
    ts: "javascript", typescript: "javascript", jsx: "javascript", mjs: "javascript",
    bash: "bash", sh: "bash", shell: "bash", zsh: "bash",
    json: "json", css: "css",
    html: "html", xml: "html", svg: "html",
    sql: "sql"
  };

  const HL_RULES = {
    python: [
      ["c", /#[^\n]*/],
      ["s", /(?:[rbufRBUF]{0,2})(?:\x22{3}[\s\S]*?\x22{3}|\x27{3}[\s\S]*?\x27{3}|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')/],
      ["k", /\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b/],
      ["kt", /\b(?:None|True|False|self|cls)\b/],
      ["nb", /\b(?:abs|all|any|bool|bytes|dict|dir|enumerate|eval|filter|float|format|frozenset|getattr|hasattr|hash|id|input|int|isinstance|issubclass|iter|len|list|map|max|min|next|object|open|pow|print|range|repr|reversed|round|set|setattr|slice|sorted|str|sum|super|tuple|type|vars|zip)\b/],
      ["m", /\b(?:0[xXbBoO][0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b/],
      ["nf", /\b[A-Za-z_]\w*(?=\s*\()/]
    ],
    javascript: [
      ["c", /\/\/[^\n]*|\/\*[\s\S]*?\*\//],
      ["s", /`(?:\\[\s\S]|[^\\`])*`|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/],
      ["k", /\b(?:const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|new|delete|typeof|instanceof|in|of|class|extends|super|this|import|export|default|from|as|async|await|try|catch|finally|throw)\b/],
      ["kt", /\b(?:true|false|null|undefined|NaN|Infinity)\b/],
      ["m", /\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b/],
      ["nf", /\b[A-Za-z_$]\w*(?=\s*\()/],
      ["o", /=>|\.\.\./]
    ],
    bash: [
      ["c", /#[^\n]*/],
      ["s", /"(?:\\.|[^"\\])*"|'(?:[^'])*'/],
      ["k", /\b(?:if|then|else|elif|fi|for|in|do|done|while|until|case|esac|function|select|time|return|exit|local|export|declare|readonly|source)\b/],
      ["nb", /\b(?:echo|cd|ls|cat|grep|sed|awk|curl|wget|git|npm|node|python|pip|sudo|mkdir|rm|cp|mv|chmod|chown|which|set|unset|trap|printf|read|test)\b/],
      ["nv", /\$\{?[#@*?0-9A-Za-z_]+\}?|\$\(/],
      ["m", /\b\d+\b/]
    ],
    json: [
      ["s", /"(?:\\.|[^"\\])*"/],
      ["k", /\b(?:true|false|null)\b/],
      ["m", /-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/]
    ],
    css: [
      ["c", /\/\*[\s\S]*?\*\//],
      ["k", /@[a-zA-Z-]+/],
      ["nt", /-{0,2}[a-zA-Z][\w-]*(?=\s*:)/],
      ["s", /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/],
      ["m", /#[0-9a-fA-F]{3,8}\b|\b\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw|s|ms|fr|deg)?\b/]
    ],
    html: [
      ["c", /<!--[\s\S]*?-->/],
      ["nt", /<\/?[a-zA-Z][\w:-]*/],
      ["na", /\b[a-zA-Z-]+(?==)/],
      ["s", /"(?:[^"]*)"|'(?:[^']*)'/],
      ["p", /\/?>/]
    ],
    sql: [
      ["c", /--[^\n]*|\/\*[\s\S]*?\*\//],
      ["k", /\b(?:SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|DROP|ALTER|INDEX|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|ORDER|BY|LIMIT|OFFSET|HAVING|AND|OR|NOT|NULL|IS|IN|AS|DISTINCT|PRIMARY|KEY|FOREIGN|REFERENCES|DEFAULT|UNIQUE|COUNT|SUM|AVG|MIN|MAX|BEGIN|COMMIT|ROLLBACK|CASE|WHEN|THEN|ELSE|END|ASC|DESC|UNION|ALL)\b/i],
      ["s", /'(?:''|[^'])*'/],
      ["m", /\b\d+(?:\.\d+)?\b/]
    ]
  };

  function normalizeLang(l) {
    const key = String(l || "").toLowerCase().replace(/[^a-z0-9+#.-]/g, "");
    if (HL_LANG_ALIASES[key]) return HL_LANG_ALIASES[key];
    return HL_RULES[key] ? key : null;
  }

  function guessLang(src) {
    const s = String(src || "");
    if (/^#!.*\b(ba)?sh\b/m.test(s)) return "bash";
    if (/^\s*(def |class \w+\(|import \w|from \w+ import |@\w+(?:\.\w+)*\s*$)/m.test(s)) return "python";
    if (/\b(function|const|let|var)\s+[\w$]|=>\s*{|console\.(log|error)|require\(|import\s+.+\s+from/.test(s)) return "javascript";
    if (/^\s*[[{][\s\S]*[\]}]\s*$/.test(s)) {
      try { JSON.parse(s); return "json"; } catch (e) { /* not json */ }
    }
    if (/<\/?[a-zA-Z][^<>]*>/.test(s) && /<\/[a-zA-Z]+\s*>|\/>/.test(s)) return "html";
    return null;
  }

  function highlightSource(lang, src) {
    const rules = HL_RULES[normalizeLang(lang)];
    if (!rules) return null;
    const pattern = new RegExp(
      rules.map(function (r) { return "(" + r[1].source + ")"; }).join("|"),
      "g"
    );
    let out = "";
    let last = 0;
    let m;
    while ((m = pattern.exec(src)) !== null) {
      if (m[0] === "") { pattern.lastIndex++; continue; }
      let cls = null;
      for (let i = 1; i < m.length; i++) {
        if (m[i] !== undefined) { cls = rules[i - 1][0]; break; }
      }
      out += escapeHtml(src.slice(last, m.index));
      out += cls
        ? '<span class="' + cls + '">' + escapeHtml(m[0]) + "</span>"
        : escapeHtml(m[0]);
      last = m.index + m[0].length;
    }
    out += escapeHtml(src.slice(last));
    return out;
  }

  function hasTokenSpans(code) {
    return !!code.querySelector("span[class]");
  }

  function enhanceOnePre(pre) {
    const parent = pre.parentElement;
    if (parent && parent.classList && parent.classList.contains("code-block")) return;
    const code = pre.querySelector("code");
    if (code) {
      if (!hasTokenSpans(code)) {
        const raw = code.textContent;
        let lang = null;
        const lm = /(?:^|\s)language-([\w+#.-]+)/.exec(code.className || "");
        if (lm) lang = normalizeLang(lm[1]);
        if (!lang) lang = guessLang(raw);
        const html = lang ? highlightSource(lang, raw) : null;
        if (html != null) code.innerHTML = html;
        else code.textContent = raw;
      }
    }
    const wrap = document.createElement("div");
    wrap.className = "code-block";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "code-copy";
    btn.textContent = "Salin";
    btn.setAttribute("aria-label", "Salin kode");
    wrap.insertBefore(btn, pre);
  }

  function wrapTables(scope) {
    const tables = scope.querySelectorAll("table");
    for (let i = 0; i < tables.length; i++) {
      const t = tables[i];
      const p = t.parentElement;
      if (p && p.classList && p.classList.contains("table-scroll")) continue;
      const wrap = document.createElement("div");
      wrap.className = "table-scroll";
      t.parentNode.insertBefore(wrap, t);
      wrap.appendChild(t);
    }
  }

  function enhanceCodeBlocks(root) {
    const scope = root || document;
    const pres = scope.querySelectorAll("pre");
    for (let i = 0; i < pres.length; i++) enhanceOnePre(pres[i]);
    wrapTables(scope);
  }

  function copyTextToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      if (ok) resolve();
      else reject(new Error("copy failed"));
    });
  }

  function handleCopyClick(btn) {
    const block = btn.closest ? btn.closest(".code-block") : null;
    const pre = block ? block.querySelector("pre") : null;
    const code = pre ? pre.querySelector("code") : null;
    const src = code || pre;
    if (!src) return;
    const text = src.textContent.replace(/\n$/, "");
    clearTimeout(btn._copyT);
    copyTextToClipboard(text).then(function () {
      btn.textContent = "Tersalin";
      btn.classList.remove("failed");
      btn.classList.add("copied");
      btn._copyT = setTimeout(function () {
        btn.textContent = "Salin";
        btn.classList.remove("copied");
      }, 1600);
    }).catch(function () {
      btn.textContent = "Gagal";
      btn.classList.remove("copied");
      btn.classList.add("failed");
      btn._copyT = setTimeout(function () {
        btn.textContent = "Salin";
        btn.classList.remove("failed");
      }, 1600);
    });
  }

  function handleCopyLink(btn) {
    clearTimeout(btn._copyT);
    const label = btn.querySelector(".share-copy-label") || btn;
    const original = label.textContent;
    copyTextToClipboard(location.href).then(function () {
      label.textContent = "Tersalin";
      btn.classList.remove("failed");
      btn.classList.add("copied");
      btn._copyT = setTimeout(function () {
        label.textContent = original;
        btn.classList.remove("copied");
      }, 1600);
    }).catch(function () {
      label.textContent = "Gagal";
      btn.classList.remove("copied");
      btn.classList.add("failed");
      btn._copyT = setTimeout(function () {
        label.textContent = original;
        btn.classList.remove("failed");
      }, 1600);
    });
  }

  function bootShare() {
    const nativeBtn = document.getElementById ? document.getElementById("share-native") : null;
    if (nativeBtn && navigator.share) {
      nativeBtn.hidden = false;
      nativeBtn.addEventListener("click", function () {
        navigator.share({ title: document.title, url: location.href }).catch(function () {});
      });
    }
  }

  function buildToc() {
    if (typeof document.querySelector !== "function") return;
    var content = document.querySelector(".note-content.prose");
    if (!content || !content.parentNode || typeof document.createElement !== "function") return;
    if (document.querySelector(".toc")) return;
    var heads = content.querySelectorAll ? content.querySelectorAll("h2, h3") : [];
    if (!heads || heads.length < 2) return;

    var used = {};
    var items = [];
    for (var i = 0; i < heads.length; i++) {
      var h = heads[i];
      var text = (h.textContent || "").trim();
      var base = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      var id = base || "bagian-" + (i + 1);
      var n = 2;
      while (used[id] || document.getElementById(id)) {
        id = (base || "bagian-" + (i + 1)) + "-" + n++;
      }
      used[id] = true;
      h.id = id;
      items.push({ id: id, text: text, level: h.tagName === "H3" ? 3 : 2 });
    }

    var nav = document.createElement("nav");
    nav.className = "toc";
    nav.setAttribute("aria-label", "Daftar Isi");

    function loadCollapsed() {
      try {
        var store = typeof localStorage !== "undefined" ? localStorage : window && window.localStorage;
        return !!store && store.getItem("toc-collapsed") === "1";
      } catch (e) {
        return false;
      }
    }
    function saveCollapsed(c) {
      try {
        var store = typeof localStorage !== "undefined" ? localStorage : window && window.localStorage;
        if (store) store.setItem("toc-collapsed", c ? "1" : "0");
      } catch (e) {}
    }

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toc-title";
    btn.setAttribute("aria-expanded", "true");
    var icon = document.createElement("i");
    icon.className = "fa-solid fa-list";
    icon.setAttribute("aria-hidden", "true");
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(" Daftar Isi"));
    var chev = document.createElement("i");
    chev.className = "fa-solid fa-chevron-down toc-chevron";
    chev.setAttribute("aria-hidden", "true");
    btn.appendChild(chev);
    var ul = document.createElement("ul");
    ul.className = "toc-list";
    var links = [];
    items.forEach(function (it) {
      var li = document.createElement("li");
      li.className = it.level === 3 ? "toc-l3" : "toc-l2";
      var a = document.createElement("a");
      a.href = "#" + it.id;
      a.textContent = it.text;
      li.appendChild(a);
      ul.appendChild(li);
      links.push({ a: a, id: it.id });
    });
    nav.appendChild(btn);
    nav.appendChild(ul);
    content.parentNode.insertBefore(nav, content);

    function applyTocCollapsed(c) {
      nav.classList.toggle("collapsed", c);
      btn.setAttribute("aria-expanded", c ? "false" : "true");
    }
    applyTocCollapsed(loadCollapsed());
    if (btn.addEventListener) {
      btn.addEventListener("click", function () {
        var c = !nav.classList.contains("collapsed");
        applyTocCollapsed(c);
        saveCollapsed(c);
      });
    }

    var ticking = false;
    function spy() {
      ticking = false;
      var activeLink = links.length ? links[0].a : null;
      for (var j = 0; j < links.length; j++) {
        var el = document.getElementById(links[j].id);
        if (el && el.getBoundingClientRect().top <= 120) activeLink = links[j].a;
      }
      for (var k = 0; k < links.length; k++) {
        links[k].a.classList.toggle("active", links[k].a === activeLink);
      }
    }
    if (window.addEventListener) {
      window.addEventListener(
        "scroll",
        function () {
          if (!ticking) {
            ticking = true;
            if (window.requestAnimationFrame) window.requestAnimationFrame(spy);
            else spy();
          }
        },
        { passive: true }
      );
    }
    spy();
  }

  // Delegated confirm dialogs (CSP-safe, no inline handlers)
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    const msg = form.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) {
      e.preventDefault();
    }
  });
  document.addEventListener("click", function (e) {
    const copyBtn = e.target && e.target.closest ? e.target.closest(".code-copy") : null;
    if (copyBtn) {
      e.preventDefault();
      handleCopyClick(copyBtn);
      return;
    }
    const linkBtn = e.target && e.target.closest ? e.target.closest("[data-copy-link]") : null;
    if (linkBtn) {
      e.preventDefault();
      handleCopyLink(linkBtn);
      return;
    }
    const btn = e.target && e.target.closest ? e.target.closest("[data-confirm][type='submit'], button[data-confirm]") : null;
    if (btn) {
      if (btn.form && btn.form.hasAttribute("data-confirm")) return;
      const msg = btn.getAttribute("data-confirm");
      if (msg && !window.confirm(msg)) {
        e.preventDefault();
        return;
      }
    }
    const back = e.target && e.target.closest ? e.target.closest("[data-history-back]") : null;
    if (back) {
      e.preventDefault();
      if (window.history.length > 1) window.history.back();
      else window.location.href = "/";
    }
  });

  window.mdToHtml = mdToHtml;
  window.enhanceCodeBlocks = enhanceCodeBlocks;

  function bootEnhance() {
    enhanceCodeBlocks(document);
    bootShare();
    buildToc();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootEnhance);
  } else {
    bootEnhance();
  }
})();
