(function () {
  "use strict";

  const editor = document.getElementById("md-editor");
  if (!editor) return;
  const preview = document.getElementById("md-preview");
  const stats = document.getElementById("md-stats");
  const tabs = document.querySelectorAll("[data-editor-tab]");

  function updateStats() {
    const words = (editor.value.trim().match(/\S+/g) || []).length;
    const mins = words ? Math.max(1, Math.round(words / 200)) : 0;
    stats.textContent = words + " kata · ~" + mins + " menit baca";
  }

  tabs.forEach(function (btn) {
    btn.addEventListener("click", function () {
      tabs.forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      renderActiveTab();
    });
  });

  function renderPreview(text) {
    preview.innerHTML = window.mdToHtml
      ? window.mdToHtml(text)
      : '<p class="muted">Preview markdown.</p>';
    if (window.enhanceCodeBlocks) window.enhanceCodeBlocks(preview);
  }

  function renderActiveTab() {
    const active = document.querySelector("[data-editor-tab].active");
    const mode = active ? active.getAttribute("data-editor-tab") : "write";
    if (mode === "preview") {
      renderPreview(editor.value);
      preview.hidden = false;
      editor.hidden = true;
    } else {
      preview.hidden = true;
      editor.hidden = false;
    }
  }

  // Keep preview in sync while editing if preview tab is open
  editor.addEventListener("input", function () {
    updateStats();
    scheduleAudit();
    if (!preview.hidden) {
      renderPreview(editor.value);
    }
  });
  updateStats();

  const coverInput = document.getElementById("cover-input");
  const coverUrl = document.getElementById("cover_url");
  const coverStorage = document.getElementById("cover_storage");
  const coverPath = document.getElementById("cover_path");
  const coverFileId = document.getElementById("cover_file_id");
  const coverPreview = document.getElementById("cover-preview");
  const coverStatus = document.getElementById("cover-status");
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrf = csrfMeta ? csrfMeta.content : "";

  const NOTE_ID =
    (typeof location !== "undefined" &&
      ((location.pathname.match(/\/admin\/catatan\/([0-9a-f]{24})\/edit/) || [])[1])) ||
    "";
  const sessionUploads = new Set();
  let auditTimer = 0;

  function absentUploads() {
    const text = editor ? editor.value : "";
    const cover = coverUrl ? coverUrl.value || "" : "";
    const out = [];
    sessionUploads.forEach(function (u) {
      if (u && !text.includes(u) && u !== cover) out.push(u);
    });
    return out;
  }

  function purgeAbsent(useBeacon) {
    absentUploads().forEach(function (u) {
      sessionUploads.delete(u);
      const body =
        "url=" + encodeURIComponent(u) + (NOTE_ID ? "&note_id=" + NOTE_ID : "");
      if (
        useBeacon &&
        typeof navigator !== "undefined" &&
        navigator.sendBeacon &&
        typeof Blob !== "undefined"
      ) {
        try {
          navigator.sendBeacon(
            "/admin/media/hapus",
            new Blob([body + "&csrf_token=" + encodeURIComponent(csrf)], {
              type: "application/x-www-form-urlencoded",
            })
          );
          return;
        } catch (e) {}
      }
      if (typeof fetch === "function") {
        fetch("/admin/media/hapus", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRF-Token": csrf,
          },
          body: body,
        }).catch(function () {});
      }
    });
  }

  function scheduleAudit() {
    clearTimeout(auditTimer);
    auditTimer = setTimeout(function () {
      purgeAbsent(false);
    }, 1500);
  }

  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("beforeunload", function () {
      purgeAbsent(true);
    });
  }

  function dispatchInput() {
    editor.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function insertAtCursor(text) {
    const s = editor.selectionStart;
    const e = editor.selectionEnd;
    editor.setRangeText(text, s, e, "end");
    dispatchInput();
    editor.focus();
  }

  function wrapSelection(pre, post, placeholder) {
    const v = editor.value;
    const s = editor.selectionStart;
    const e = editor.selectionEnd;
    const sel = v.slice(s, e);
    if (v.slice(s - pre.length, s) === pre && v.slice(e, e + post.length) === post) {
      editor.value = v.slice(0, s - pre.length) + sel + v.slice(e + post.length);
      editor.setSelectionRange(s - pre.length, s - pre.length + sel.length);
      dispatchInput();
      editor.focus();
      return;
    }
    const ins = sel || placeholder;
    editor.value = v.slice(0, s) + pre + ins + post + v.slice(e);
    editor.setSelectionRange(s + pre.length, s + pre.length + ins.length);
    dispatchInput();
    editor.focus();
  }

  function linePrefix(prefix) {
    const v = editor.value;
    const s = editor.selectionStart;
    const e = editor.selectionEnd;
    const ls = v.lastIndexOf("\n", s - 1) + 1;
    let le = v.indexOf("\n", e);
    if (le === -1) le = v.length;
    const lines = v.slice(ls, le).split("\n");
    const already = lines.every((l) => l.indexOf(prefix) === 0);
    const out = lines.map((l) => (already ? l.slice(prefix.length) : prefix + l)).join("\n");
    editor.value = v.slice(0, ls) + out + v.slice(le);
    editor.setSelectionRange(ls, ls + out.length);
    dispatchInput();
    editor.focus();
  }

  const mdActions = {
    bold: () => wrapSelection("**", "**", "tebal"),
    italic: () => wrapSelection("*", "*", "miring"),
    heading: () => linePrefix("## "),
    link: () => wrapSelection("[", "](https://)", "tautan"),
    code: () => wrapSelection("`", "`", "kode"),
    codeblock: () => wrapSelection("```\n", "\n```", "kode"),
    list: () => linePrefix("- "),
    quote: () => linePrefix("> "),
    table: () => insertAtCursor("\n| Kolom 1 | Kolom 2 |\n| --- | --- |\n|  |  |\n"),
    hr: () => insertAtCursor("\n\n---\n\n"),
  };
  document.querySelectorAll("[data-md]").forEach((btn) => {
    const fn = mdActions[btn.getAttribute("data-md")];
    if (fn) btn.addEventListener("click", fn);
  });

  const editorStatus = document.getElementById("editor-status");
  let statusTimer = null;
  function setStatus(msg) {
    if (!editorStatus) return;
    editorStatus.textContent = msg ? "· " + msg : "";
    clearTimeout(statusTimer);
    if (msg) {
      statusTimer = setTimeout(() => {
        editorStatus.textContent = "";
      }, 5000);
    }
  }

  function uploadImage(file) {
    if (file.size > 5 * 1024 * 1024) {
      setStatus("Gambar melebihi 5MB.");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    setStatus("Mengunggah gambar…");
    fetch("/admin/upload", {
      method: "POST",
      headers: { "X-CSRF-Token": csrf },
      body: fd,
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.ok) {
          setStatus(
            data.error === "csrf"
              ? "Token kedaluwarsa. Muat ulang halaman."
              : data.error || "Upload gagal."
          );
          return;
        }
        const alt = (file.name || "gambar").replace(/\.[^.]+$/, "");
        insertAtCursor("\n![" + alt + "](" + data.url + ")\n");
        if (data.url) sessionUploads.add(data.url);
        setStatus("Gambar terunggah.");
      })
      .catch(() => setStatus("Upload gagal."));
  }

  function pickImage(files) {
    if (!files) return null;
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      if (f.type && f.type.indexOf("image/") === 0) return f;
    }
    return null;
  }

  editor.addEventListener("paste", (e) => {
    const img = pickImage(e.clipboardData && e.clipboardData.files);
    if (!img) return;
    e.preventDefault();
    uploadImage(img);
  });

  editor.addEventListener("drop", (e) => {
    const img = pickImage(e.dataTransfer && e.dataTransfer.files);
    if (!img) return;
    e.preventDefault();
    uploadImage(img);
  });

  const form = editor.form;
  if (form) {
    form.addEventListener("submit", function () {
      purgeAbsent(true);
    });
    const DRAFT_KEY = "catatan-draft:" + location.pathname;
    const draftStatus = document.getElementById("draft-status");
    let draftTimer = null;

    function collectForm() {
      const pick = (name) => {
        const el = form.querySelector('[name="' + name + '"]');
        if (!el) return "";
        return el.type === "checkbox" ? (el.checked ? "1" : "") : el.value;
      };
      return {
        title: pick("title"),
        excerpt: pick("excerpt"),
        content: pick("content"),
        tags: pick("tags"),
        category_id: pick("category_id"),
        status: pick("status"),
        is_pinned: pick("is_pinned"),
        cover_url: pick("cover_url"),
        cover_storage: pick("cover_storage"),
        cover_path: pick("cover_path"),
        cover_file_id: pick("cover_file_id"),
      };
    }

    function applyForm(v) {
      Object.keys(v).forEach((name) => {
        const el = form.querySelector('[name="' + name + '"]');
        if (!el) return;
        if (el.type === "checkbox") el.checked = !!v[name];
        else el.value = v[name] == null ? "" : v[name];
      });
      if (v.cover_url && coverPreview) {
        coverPreview.innerHTML = "";
        const img = document.createElement("img");
        img.src = v.cover_url;
        img.alt = "Sampul";
        coverPreview.appendChild(img);
      }
      updateStats();
      if (!preview.hidden) renderPreview(editor.value);
    }

    const initial = JSON.stringify(collectForm());
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    } catch (err) {
      saved = null;
    }

    if (/[?&](saved|created)=1/.test(location.search)) {
      localStorage.removeItem(DRAFT_KEY);
      saved = null;
    }
    if (saved && saved.v && JSON.stringify(saved.v) !== initial) {
      const when = saved.t ? new Date(saved.t).toLocaleString("id-ID") : "";
      if (window.confirm("Draf lokal ditemukan (diubah " + when + "). Pulihkan ke form?")) {
        applyForm(saved.v);
        if (draftStatus) draftStatus.textContent = "· Draf lokal dipulihkan";
      } else {
        localStorage.removeItem(DRAFT_KEY);
      }
    }

    function saveDraft() {
      const data = collectForm();
      if (JSON.stringify(data) === initial) {
        localStorage.removeItem(DRAFT_KEY);
        if (draftStatus) draftStatus.textContent = "";
        return;
      }
      try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify({ t: Date.now(), v: data }));
        if (draftStatus) {
          draftStatus.textContent =
            "· Draf lokal tersimpan " +
            new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
        }
      } catch (err) {
        /* storage penuh/di-block */
      }
    }

    form.addEventListener("input", () => {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(saveDraft, 1200);
    });
  }

  if (!coverInput) return;

  coverInput.addEventListener("change", async function () {
    const file = coverInput.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      coverStatus.textContent = "Ukuran file melebihi 5MB.";
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    coverStatus.textContent = "Mengunggah…";
    try {
      const res = await fetch("/admin/upload", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        coverStatus.textContent =
          data.error === "csrf"
            ? "Token keamanan kedaluwarsa. Muat ulang halaman lalu coba lagi."
            : data.error || "Upload gagal.";
        return;
      }
      coverUrl.value = data.url || "";
      if (data.url) sessionUploads.add(data.url);
      coverStorage.value = data.storage || "";
      coverPath.value = data.path || "";
      coverFileId.value = data.file_id || "";
      coverPreview.innerHTML = "";
      const img = document.createElement("img");
      img.src = data.url || "";
      img.alt = "Sampul";
      coverPreview.appendChild(img);
      coverStatus.textContent = "Tersimpan (" + (data.storage || "local") + ").";
      scheduleAudit();
    } catch (e) {
      coverStatus.textContent = "Upload gagal.";
    }
  });
})();
