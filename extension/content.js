(() => {
  if (window.__rqsLoaded) {
    window.__rqsTrigger();
    return;
  }
  window.__rqsLoaded = true;

  const BACKEND_URL = "https://recruter-exten.vercel.app/lookup";

  async function triggerSearch() {
    // 1. Context menu pre-set text (from background.js)
    if (window.__rqsSelectedText) {
      var txt = window.__rqsSelectedText;
      window.__rqsSelectedText = null;
      showPopup('Searching for "' + escapeHtml(txt) + '"...', false, false);
      fetchCompanyInfo(txt, false);
      return;
    }

    // 2. Try standard DOM selection (works on normal web pages)
    var text = window.getSelection().toString().trim();

    // 3. Clipboard fallback — for sites where selection doesn't work (Drive, Docs)
    var fromClipboard = false;
    if (!text) {
      try {
        text = await navigator.clipboard.readText();
        text = text.trim();
        fromClipboard = true;
      } catch (_) { /* clipboard read requires HTTPS + permission */ }
    }

    if (!text) {
      showPopup("Please highlight a company name first.", true, false);
      return;
    }

    showPopup('Searching for "' + escapeHtml(text) + '"...', false, fromClipboard);
    fetchCompanyInfo(text, fromClipboard);
  }

  window.__rqsTrigger = triggerSearch;

  // ── Popup ──────────────────────────────────────────────────────────

  function showPopup(content, isError, fromClipboard) {
    removePopup();

    const wrapper = document.createElement("div");
    wrapper.id = "__rqs-popup";

    const title = isError ? "Notice" : "Company Lookup";
    wrapper.innerHTML =
      '<div style="' +
      "position:fixed;top:20px;right:20px;max-width:520px;min-width:300px;" +
      "background:#fff;border:1px solid #e0e0e0;border-radius:10px;" +
      "box-shadow:0 6px 24px rgba(0,0,0,0.14);" +
      "padding:18px 20px;font-family:-apple-system,BlinkMacSystemFont," +
      "'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.6;" +
      "color:#222;z-index:2147483647;animation:rqsFadeIn .2s ease;" +
      '">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">' +
      '<strong style="font-size:15px;color:#111;">' +
      escapeHtml(title) +
      "</strong>" +
      '<button id="__rqs-close"' +
      "style=\"background:none;border:none;font-size:22px;cursor:pointer;" +
      'color:#999;padding:0 2px;line-height:1;\">&times;</button>' +
      "</div>" +
      '<div id="__rqs-body" style="font-size:13px;"></div>' +
      "</div>";

    document.body.appendChild(wrapper);

    const body = document.getElementById("__rqs-body");
    if (isError || content.startsWith("Searching for")) {
      body.textContent = content;
    } else {
      body.innerHTML = content;
    }

    document.getElementById("__rqs-close").addEventListener("click", removePopup);
    document.addEventListener("keydown", onKeyDown);

    setTimeout(function () {
      document.addEventListener("click", onClickOutside);
    }, 0);

    if (!document.getElementById("__rqs-style")) {
      var s = document.createElement("style");
      s.id = "__rqs-style";
      s.textContent =
        "@keyframes rqsFadeIn{" +
        "from{opacity:0;transform:translateY(-8px)}" +
        "to{opacity:1;transform:translateY(0)}" +
        "}" +
        "#__rqs-body .rqs-details{" +
        "margin-top:12px;padding-top:10px;border-top:1px solid #eee;" +
        "display:grid;grid-template-columns:auto 1fr;gap:4px 12px;" +
        "font-size:12px;" +
        "}" +
        "#__rqs-body .rqs-details .rqs-label{" +
        "color:#888;white-space:nowrap;" +
        "}" +
        "#__rqs-body .rqs-details .rqs-val{" +
        "color:#333;font-weight:500;" +
        "}" +
        "#__rqs-body .rqs-link{" +
        "margin-top:12px;padding-top:10px;border-top:1px solid #eee;" +
        "}" +
        "#__rqs-body .rqs-link a{" +
        "color:#0056b3;text-decoration:none;font-weight:600;font-size:13px;" +
        "}";
      document.head.appendChild(s);
    }
  }

  function removePopup() {
    var el = document.getElementById("__rqs-popup");
    if (el) el.remove();
    document.removeEventListener("keydown", onKeyDown);
    document.removeEventListener("click", onClickOutside);
  }

  function onKeyDown(e) {
    if (e.key === "Escape") removePopup();
  }

  function onClickOutside(e) {
    var popup = document.getElementById("__rqs-popup");
    if (popup && !popup.contains(e.target)) removePopup();
  }

  // ── API call ───────────────────────────────────────────────────────

  async function fetchCompanyInfo(company, fromClipboard) {
    try {
      var resp = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: company }),
      });

      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        var msg = err.detail;
        if (typeof msg === "object") {
          msg = "Validation Error: Backend expected a different data format.";
        }
        showPopup(msg || "No information found.", true);
        return;
      }

      var data = await resp.json();
      var body = document.getElementById("__rqs-body");
      if (!body) return;

      body.innerHTML = buildResultHTML(data, fromClipboard);
    } catch (e) {
      showPopup("Could not reach the backend. Check your connection.", true);
    }
  }

  // ── Build result HTML ──────────────────────────────────────────────

  function buildResultHTML(data, fromClipboard) {
    var html = "";

    // Summary + cached badge
    var summary = data.summary || "No summary found.";
    html += '<div class="rqs-summary">' + escapeHtml(summary);
    if (data.cached) {
      html +=
        ' <span style="background:#e8f5e9;color:#2e7d32;font-size:10px;' +
        'padding:1px 6px;border-radius:3px;margin-left:6px;vertical-align:middle;">' +
        "cached</span>";
    }
    html += "</div>";

    // Clipboard hint — shown when user searched via clipboard (Drive, Docs)
    if (fromClipboard) {
      html +=
        '<div style="background:#fff3e0;color:#e65100;font-size:11px;' +
        'padding:6px 10px;margin:8px 0 4px 0;border-radius:4px;' +
        'border-left:3px solid #ff9800;">' +
        "Tip: On this page, use <b>Ctrl+C</b> to copy text, " +
        "then <b>Ctrl+Shift+Y</b> to search.</div>";
    }

    // Details as bullet points
    var details = data.details;
    if (details && Object.keys(details).length > 0) {
      html += '<div class="rqs-details">';

      var labels = {
        founding_year: "Founded",
        headquarters: "Headquarters",
        size: "Size",
        revenue: "Revenue",
        last_funding: "Funding",
        industry: "Industry",
        leadership: "Leadership",
        clients: "Clients",
      };

      var keys = Object.keys(labels);
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        var val = details[k];
        if (val && val !== "Not found") {
          html +=
            '<span class="rqs-label">' +
            escapeHtml(labels[k]) +
            ":</span>" +
            '<span class="rqs-val">' +
            escapeHtml(val) +
            "</span>";
        }
      }
      html += "</div>";
    }

    // Link
    if (data.link) {
      html +=
        '<div class="rqs-link">' +
        '<a href="' +
        escapeHtml(data.link) +
        '" target="_blank" rel="noopener noreferrer">Visit Official Website</a>' +
        "</div>";
    }

    return html;
  }

  // ── Helpers ────────────────────────────────────────────────────────

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ── Message listener (context menu results from background) ──────────

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg.type === "showResult" && msg.data) {
      var body = document.getElementById("__rqs-body");
      if (body) {
        body.innerHTML = buildResultHTML(msg.data, false);
      } else {
        // No existing popup — create one
        showResultPopup(msg.data);
      }
    } else if (msg.type === "showError") {
      showPopup(msg.message || "An error occurred.", true);
    }
  });

  function showResultPopup(data) {
    showPopup("", false);
    var body = document.getElementById("__rqs-body");
    if (body) {
      body.innerHTML = buildResultHTML(data);
    }
  }

  triggerSearch();
})();
