// ── Context menu: right-click to search ──────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "search-company",
    title: "Search highlighted company",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "search-company" && info.selectionText) {
    injectContentScript(tab);
  }
});

// ── Toolbar icon click + keyboard shortcut ───────────────────────────

chrome.action.onClicked.addListener(async (tab) => {
  injectContentScript(tab);
});

// ── Shared injection ─────────────────────────────────────────────────

async function injectContentScript(tab) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: ["content.js"],
    });
  } catch (err) {
    console.error("Recruiter Quick Search: cannot inject into this page.", err);
  }
}
