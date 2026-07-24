// Context menu — always works, including in cross-origin iframes
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "rqs_search",
    title: "Search company: %s",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "rqs_search") return;
  if (!info.selectionText) return;

  try {
    // Context menu gives us selectionText directly — no clipboard needed
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (text) => {
        window.__rqsSelectedText = text;
      },
      args: [info.selectionText],
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    console.error("Recruiter Quick Search: context menu injection failed.", err);
  }
});

// Toolbar click + keyboard shortcut (Ctrl+Shift+Y)
chrome.action.onClicked.addListener(async (tab) => {
  try {
    // Step 1: Capture text in-page while user gesture is still active.
    // This is injected via func() so the gesture token carries through.
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: captureSelection,
    });

    // Step 2: Inject content.js to display results
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    console.error("Recruiter Quick Search: cannot inject.", err);
  }
});

// This function runs in the page context immediately after the shortcut/keypress.
// The user gesture is still active, so execCommand("copy") works on Drive/Docs.
async function captureSelection() {
  // 1. Try standard DOM selection (normal pages)
  let text = window.getSelection().toString().trim();

  // 2. If empty (Google Drive, Docs, canvas viewers):
  //    Save clipboard -> copy selection -> read clipboard -> restore
  if (!text) {
    let oldClip = "";
    try {
      oldClip = await navigator.clipboard.readText();
    } catch (_) {}

    // Force copy — Google Drive/Docs intercepts this and fills clipboard
    document.execCommand("copy");

    // Wait for the clipboard to update
    await new Promise(r => setTimeout(r, 150));

    try {
      text = await navigator.clipboard.readText();
      text = text.trim();
    } catch (_) {}

    // Restore original clipboard content
    if (oldClip && text && oldClip !== text) {
      try {
        await navigator.clipboard.writeText(oldClip);
      } catch (_) {}
    }
  }

  window.__rqsSelectedText = text || "";
}
