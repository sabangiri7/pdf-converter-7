/* Vanilla JS: drag-and-drop file selection + spinner on submit.
 * Works on every tool page that uses the shared _form.html macro.
 * No dependencies. */
(function () {
  "use strict";

  function listFiles(input) {
    var list = input.closest(".dropzone").querySelector(".file-list");
    list.innerHTML = "";
    Array.prototype.forEach.call(input.files, function (f) {
      var li = document.createElement("li");
      li.textContent = f.name + " (" + (f.size / 1024 / 1024).toFixed(2) + " MB)";
      list.appendChild(li);
    });
  }

  function wireDropzone(zone) {
    var input = zone.querySelector('input[type="file"]');
    if (!input) return;

    input.addEventListener("change", function () { listFiles(input); });

    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault(); e.stopPropagation();
        zone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault(); e.stopPropagation();
        zone.classList.remove("dragover");
      });
    });
    zone.addEventListener("drop", function (e) {
      var dt = e.dataTransfer;
      if (!dt || !dt.files || !dt.files.length) return;
      try {
        // native FileList -> DataTransfer keeps the input valid
        var store = new DataTransfer();
        var accept = (zone.dataset.accept || "").split(",").map(function (s) {
          return s.trim().toLowerCase();
        }).filter(Boolean);
        var allowAny = accept.length === 0 || accept.indexOf("*") !== -1 ||
          accept.join(",").indexOf(".") === -1;
        Array.prototype.forEach.call(dt.files, function (f) {
          var lname = f.name.toLowerCase();
          var ok = allowAny || accept.some(function (ext) {
            return lname.slice(-ext.length) === ext;
          });
          if (ok) store.items.add(f);
        });
        input.files = store.files;
      } catch (err) {
        input.files = dt.files; // older browsers
      }
      listFiles(input);
      // Notify tool-specific listeners (e.g. Organize PDF preview)
      try {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (_) {}
    });
  }

  function wireForm(form) {
    form.addEventListener("submit", function (e) {
      if (form.checkValidity && !form.checkValidity()) return; // let native validation speak
      form.classList.add("submitting");
      var btn = form.querySelector(".submit-btn");
      if (btn) btn.disabled = true;
      // submission continues; page blocks until the result arrives
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".dropzone").forEach(wireDropzone);
    document.querySelectorAll("form.tool-form").forEach(wireForm);
  });
})();
