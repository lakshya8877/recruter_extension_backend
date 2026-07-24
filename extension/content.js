(() => {
  // ── 1. Fixed URL (Removed double slash) ─────────────────────────────────
  const BACKEND_URL = "https://recruter-exten.vercel.app/lookup";
  // ────────────────────────────────────────────────────────────────────────

  function triggerSearch() {
    const text = window.getSelection().toString().trim();
    if (!text) {
      showPopup("⚠️ Please highlight a company name first.", true);
      return;
    }
    showPopup(`⏳ Searching for "${text}"...`, false);
    fetchCompanyInfo(text);
  }

  // ── Popup ──────────────────────────────────────────────────────────────

  function showPopup(content, isError) {
    removePopup();

    const wrapper = document.createElement("div");
    wrapper.id = "__rqs-popup";

    const title = isError ? "Notice" : "Company Lookup";
    wrapper.innerHTML = `
      <div style="
        position:fixed;top:20px;right:20px;max-width:400px;min-width:260px;
        background:#fff;border:1px solid #e0e0e0;border-radius:10px;
        box-shadow:0 6px 24px rgba(0,0,0,0.14);
        padding:18px 20px;font-family:-apple-system,BlinkMacSystemFont,
        'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.6;
        color:#222;z-index:2147483647;animation:rqsFadeIn .2s ease;
      ">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <strong style="font-size:15px;color:#111;">${escapeHtml(title)}</strong>
          <button id="__rqs-close"
            style="background:none;border:none;font-size:22px;cursor:pointer;
            color:#999;padding:0 2px;line-height:1;">&times;</button>
        </div>
        <div id="__rqs-body">${escapeHtml(content)}</div>
      </div>
    `;

    document.body.appendChild(wrapper);

    document.getElementById("__rqs-close").addEventListener("click", removePopup);

    // Dismiss on Esc
    document.addEventListener("keydown", onKeyDown);

    // Inject fade-in keyframe once
    if (!document.getElementById("__rqs-style")) {
      const style = document.createElement("style");
      style.id = "__rqs-style";
      style.textContent =
        "@keyframes rqsFadeIn{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}";
      document.head.appendChild(style);
    }
  }

  function removePopup() {
    const el = document.getElementById("__rqs-popup");
    if (el) el.remove();
    document.removeEventListener("keydown", onKeyDown);
  }

  function onKeyDown(e) {
    if (e.key === "Escape") removePopup();
  }

// ── API call ───────────────────────────────────────────────────────────

  async function fetchCompanyInfo(company) {
    try {
      const resp = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Reverted back to what your Python backend expects!
        body: JSON.stringify({ company: company }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        // If FastAPI throws a validation error, err.detail is an array (object). 
        let errorMsg = err.detail;
        if (typeof errorMsg === "object") {
           errorMsg = "Validation Error: Backend expected a different data format.";
        }
        showPopup(`❌ ${errorMsg || "No information found."}`, true);
        return;
      }

      const data = await resp.json();
      const body = document.getElementById("__rqs-body");
      
      if (body) {
        let finalText = data.summary;
        if (typeof finalText === "object" && finalText !== null) {
          finalText = finalText.description || finalText.snippet || JSON.stringify(finalText);
        }
        body.textContent = finalText || "No summary found.";
      }
    } catch {
      showPopup("❌ Could not reach the backend. Check your connection.", true);
    }
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Trigger the flow immediately when the script is injected
  triggerSearch();

})();