(() => {
  // Injection guard — avoid duplicate handlers on repeat triggers
  if (window.__rqsLoaded) {
    window.__rqsTrigger();
    return;
  }
  window.__rqsLoaded = true;

  const BACKEND_URL = "https://recruter-exten.vercel.app/lookup";

  function triggerSearch() {
    const text = window.getSelection().toString().trim();
    if (!text) {
      showPopup("Please highlight a company name first.", true);
      return;
    }
    showPopup('Searching for "' + escapeHtml(text) + '"...', false);
    fetchCompanyInfo(text);
  }

  // Expose for injection guard re-trigger
  window.__rqsTrigger = triggerSearch;

  // ── Popup ──────────────────────────────────────────────────────────────

  function showPopup(content, isError) {
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

    // Render content — use innerHTML for formatted text, textContent for raw
    const body = document.getElementById("__rqs-body");
    if (isError || content.startsWith("Searching for")) {
      body.textContent = content;
    } else {
      body.innerHTML = formatContent(content);
    }

    document
      .getElementById("__rqs-close")
      .addEventListener("click", removePopup);

    document.addEventListener("keydown", onKeyDown);

    // Click-outside dismissal
    setTimeout(() => {
      document.addEventListener("click", onClickOutside);
    }, 0);

    if (!document.getElementById("__rqs-style")) {
      const style = document.createElement("style");
      style.id = "__rqs-style";
      style.textContent =
        "@keyframes rqsFadeIn{" +
        "from{opacity:0;transform:translateY(-8px)}" +
        "to{opacity:1;transform:translateY(0)}" +
        "}" +
        "#__rqs-body strong{color:#1a1a1a;}" +
        "#__rqs-body .rqs-link{" +
        "display:block;margin-top:14px;padding-top:10px;" +
        "border-top:1px solid #eee;" +
        "}" +
        "#__rqs-body .rqs-link a{" +
        "color:#0056b3;text-decoration:none;font-weight:600;font-size:13px;" +
        "}";
      document.head.appendChild(style);
    }
  }

  function removePopup() {
    const el = document.getElementById("__rqs-popup");
    if (el) el.remove();
    document.removeEventListener("keydown", onKeyDown);
    document.removeEventListener("click", onClickOutside);
  }

  function onKeyDown(e) {
    if (e.key === "Escape") removePopup();
  }

  function onClickOutside(e) {
    const popup = document.getElementById("__rqs-popup");
    if (popup && !popup.contains(e.target)) {
      removePopup();
    }
  }

  // ── API call ───────────────────────────────────────────────────────────

  async function fetchCompanyInfo(company) {
    try {
      const resp = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: company }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        let errorMsg = err.detail;
        if (typeof errorMsg === "object") {
          errorMsg = "Validation Error: Backend expected a different data format.";
        }
        showPopup(errorMsg || "No information found.", true);
        return;
      }

      const data = await resp.json();
      const body = document.getElementById("__rqs-body");

      if (body) {
        let summary = data.summary;
        if (typeof summary === "object" && summary !== null) {
          summary =
            summary.description ||
            summary.snippet ||
            JSON.stringify(summary);
        }

        body.innerHTML = formatContent(summary || "No summary found.");

        // Append link below the summary if available
        if (data.link) {
          const linkWrap = document.createElement("div");
          linkWrap.className = "rqs-link";

          const a = document.createElement("a");
          a.href = data.link;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = "Visit Official Website";

          linkWrap.appendChild(a);
          body.appendChild(linkWrap);
        }
      }
    } catch {
      showPopup("Could not reach the backend. Check your connection.", true);
    }
  }

  // ── Content formatting ─────────────────────────────────────────────────

  function formatContent(text) {
    // Convert **bold** markers to <strong> tags
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // Preserve line breaks
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  triggerSearch();
})();
