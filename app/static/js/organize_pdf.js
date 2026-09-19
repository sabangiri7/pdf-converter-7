/* Organize PDF: client-side page thumbnails via PDF.js.
 * Edit order / delete pages before submit; writes hidden `pages` (e.g. "3,1,2"). */
(function () {
  "use strict";

  var PDFJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  var THUMB_SCALE = 0.28;
  var MAX_PREVIEW_PAGES = 200;

  var form = document.querySelector("form.tool-form");
  if (!form) return;

  var fileInput = form.querySelector('#files, input[type="file"]');
  var pagesInput = document.getElementById("pages");
  var ui = document.getElementById("organize-ui");
  var listEl = document.getElementById("organize-pages");
  var statusEl = document.getElementById("organize-status");
  var errorEl = document.getElementById("organize-error");
  var orderEl = document.getElementById("organize-order");
  var resetBtn = document.getElementById("organize-reset");
  if (!fileInput || !pagesInput || !ui || !listEl) return;

  var pdfDoc = null;
  var thumbCache = {};
  var entries = [];
  var uidSeq = 0;
  var dragSrcId = null;
  var loadToken = 0;

  if (typeof pdfjsLib !== "undefined") {
    pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_CDN + "pdf.worker.min.js";
  }

  function showError(msg) {
    if (!errorEl) return;
    if (msg) {
      errorEl.textContent = msg;
      errorEl.hidden = false;
    } else {
      errorEl.textContent = "";
      errorEl.hidden = true;
    }
  }

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg || "";
  }

  function syncPagesField() {
    var order = entries.map(function (e) { return e.pageNum; });
    pagesInput.value = order.join(",");
    if (orderEl) {
      orderEl.textContent = order.length
        ? "Page order: " + order.join(", ")
        : "No pages selected — add or restore pages before organizing.";
    }
  }

  function clearPreview() {
    pdfDoc = null;
    thumbCache = {};
    entries = [];
    listEl.innerHTML = "";
    ui.hidden = true;
    pagesInput.value = "";
    if (orderEl) orderEl.textContent = "";
    setStatus("");
    showError("");
  }

  function friendlyLoadError(err) {
    var name = (err && err.name) || "";
    var msg = (err && err.message) || String(err || "");
    if (name === "PasswordException" || /password/i.test(msg)) {
      return "This PDF is password-protected. Unlock it first, then organize.";
    }
    if (name === "InvalidPDFException" || /invalid pdf|missing PDF/i.test(msg)) {
      return "That file doesn't look like a readable PDF. It may be corrupted.";
    }
    return "Could not preview this PDF in the browser. Check the file and try again.";
  }

  function renderThumb(pageNum, canvas) {
    if (!pdfDoc || !canvas) return Promise.resolve();
    if (thumbCache[pageNum]) {
      var cached = thumbCache[pageNum];
      canvas.width = cached.width;
      canvas.height = cached.height;
      canvas.getContext("2d").drawImage(cached, 0, 0);
      return Promise.resolve();
    }
    return pdfDoc.getPage(pageNum).then(function (page) {
      var viewport = page.getViewport({ scale: THUMB_SCALE });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      var ctx = canvas.getContext("2d");
      return page.render({ canvasContext: ctx, viewport: viewport }).promise
        .then(function () {
          var off = document.createElement("canvas");
          off.width = canvas.width;
          off.height = canvas.height;
          off.getContext("2d").drawImage(canvas, 0, 0);
          thumbCache[pageNum] = off;
        });
    });
  }

  function moveEntry(id, delta) {
    var i = entries.findIndex(function (e) { return e.id === id; });
    if (i < 0) return;
    var j = i + delta;
    if (j < 0 || j >= entries.length) return;
    var tmp = entries[i];
    entries[i] = entries[j];
    entries[j] = tmp;
    paintList();
  }

  function removeEntry(id) {
    entries = entries.filter(function (e) { return e.id !== id; });
    paintList();
  }

  function duplicateEntry(id) {
    var i = entries.findIndex(function (e) { return e.id === id; });
    if (i < 0) return;
    var copy = { id: "p" + (++uidSeq), pageNum: entries[i].pageNum };
    entries.splice(i + 1, 0, copy);
    paintList();
  }

  function onDragStart(e) {
    var li = e.currentTarget;
    dragSrcId = li.dataset.id;
    li.classList.add("is-dragging");
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", dragSrcId); } catch (_) {}
  }

  function onDragEnd(e) {
    e.currentTarget.classList.remove("is-dragging");
    listEl.querySelectorAll(".organize-page").forEach(function (el) {
      el.classList.remove("drag-over");
    });
    dragSrcId = null;
  }

  function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    var li = e.currentTarget;
    if (li.dataset.id !== dragSrcId) li.classList.add("drag-over");
  }

  function onDragLeave(e) {
    e.currentTarget.classList.remove("drag-over");
  }

  function onDrop(e) {
    e.preventDefault();
    var target = e.currentTarget;
    target.classList.remove("drag-over");
    var fromId = dragSrcId || (function () {
      try { return e.dataTransfer.getData("text/plain"); } catch (_) { return null; }
    })();
    var toId = target.dataset.id;
    if (!fromId || !toId || fromId === toId) return;
    var from = entries.findIndex(function (x) { return x.id === fromId; });
    var to = entries.findIndex(function (x) { return x.id === toId; });
    if (from < 0 || to < 0) return;
    var item = entries.splice(from, 1)[0];
    entries.splice(to, 0, item);
    paintList();
  }

  function paintList() {
    listEl.innerHTML = "";
    entries.forEach(function (entry, index) {
      var li = document.createElement("li");
      li.className = "organize-page";
      li.dataset.id = entry.id;
      li.draggable = true;
      li.setAttribute("aria-label", "Page " + entry.pageNum + ", position " + (index + 1));

      var canvas = document.createElement("canvas");
      canvas.className = "organize-thumb";
      canvas.setAttribute("aria-hidden", "true");

      var badge = document.createElement("span");
      badge.className = "organize-badge";
      badge.textContent = String(entry.pageNum);

      var meta = document.createElement("div");
      meta.className = "organize-meta";
      meta.innerHTML = "<span class=\"organize-pos\">#" + (index + 1) +
        "</span> <span class=\"organize-src\">p." + entry.pageNum + "</span>";

      var actions = document.createElement("div");
      actions.className = "organize-page-actions";

      function mkBtn(label, title, cls, fn) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "organize-icon-btn" + (cls ? " " + cls : "");
        b.title = title;
        b.setAttribute("aria-label", title);
        b.textContent = label;
        b.addEventListener("click", function (ev) {
          ev.preventDefault();
          fn();
        });
        return b;
      }

      actions.appendChild(mkBtn("↑", "Move up", null, function () { moveEntry(entry.id, -1); }));
      actions.appendChild(mkBtn("↓", "Move down", null, function () { moveEntry(entry.id, 1); }));
      actions.appendChild(mkBtn("＋", "Duplicate page", null, function () { duplicateEntry(entry.id); }));
      actions.appendChild(mkBtn("×", "Remove page", "is-danger", function () { removeEntry(entry.id); }));

      li.appendChild(canvas);
      li.appendChild(badge);
      li.appendChild(meta);
      li.appendChild(actions);

      li.addEventListener("dragstart", onDragStart);
      li.addEventListener("dragend", onDragEnd);
      li.addEventListener("dragover", onDragOver);
      li.addEventListener("dragleave", onDragLeave);
      li.addEventListener("drop", onDrop);

      listEl.appendChild(li);
      renderThumb(entry.pageNum, canvas).catch(function () {
        /* thumb failure — leave blank canvas */
      });
    });

    syncPagesField();
    var n = entries.length;
    setStatus(n === 0
      ? "All pages removed. Restore all to bring them back."
      : n + (n === 1 ? " page" : " pages") + " will be kept.");
    if (resetBtn) resetBtn.disabled = !pdfDoc;
  }

  function buildEntries(numPages) {
    entries = [];
    uidSeq = 0;
    for (var i = 1; i <= numPages; i++) {
      entries.push({ id: "p" + (++uidSeq), pageNum: i });
    }
  }

  function loadFile(file) {
    var token = ++loadToken;
    clearPreview();
    if (!file) return;

    if (typeof pdfjsLib === "undefined") {
      showError("PDF preview library failed to load. You can still type a page order if the field is available, or refresh the page.");
      return;
    }

    var name = (file.name || "").toLowerCase();
    if (name && name.slice(-4) !== ".pdf" && file.type !== "application/pdf") {
      showError("Please choose a PDF file.");
      return;
    }

    ui.hidden = false;
    setStatus("Loading preview…");

    file.arrayBuffer().then(function (buf) {
      if (token !== loadToken) return null;
      return pdfjsLib.getDocument({ data: new Uint8Array(buf) }).promise;
    }).then(function (pdf) {
      if (token !== loadToken || !pdf) return;
      if (pdf.numPages < 1) {
        showError("That PDF does not contain any pages.");
        ui.hidden = true;
        return;
      }
      if (pdf.numPages > MAX_PREVIEW_PAGES) {
        showError("This PDF has more than " + MAX_PREVIEW_PAGES +
          " pages. Preview is limited — please use a smaller file.");
        ui.hidden = true;
        return;
      }
      pdfDoc = pdf;
      buildEntries(pdf.numPages);
      showError("");
      paintList();
    }).catch(function (err) {
      if (token !== loadToken) return;
      pdfDoc = null;
      entries = [];
      listEl.innerHTML = "";
      pagesInput.value = "";
      showError(friendlyLoadError(err));
      setStatus("");
      ui.hidden = false;
    });
  }

  function onFileMaybeChanged() {
    var f = fileInput.files && fileInput.files[0];
    if (f) loadFile(f);
    else clearPreview();
  }

  fileInput.addEventListener("change", onFileMaybeChanged);

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      if (!pdfDoc) return;
      buildEntries(pdfDoc.numPages);
      showError("");
      paintList();
    });
  }

  form.addEventListener("submit", function (e) {
    syncPagesField();
    if (!pagesInput.value) {
      e.preventDefault();
      e.stopPropagation();
      showError("Keep at least one page, or restore all pages, before organizing.");
      form.classList.remove("submitting");
      var btn = form.querySelector(".submit-btn");
      if (btn) btn.disabled = false;
      return;
    }
    if (!fileInput.files || !fileInput.files.length) return;
    // allow submit — upload.js will show spinner
  }, true);
})();
