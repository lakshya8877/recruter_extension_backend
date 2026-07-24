// Context menu — always works, including in cross-origin iframes (Google Drive, PDF viewers)
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
    // Save the selection text so content.js can read it
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (text) => {
        window.__rqsSelectedText = text;
        window.__rqsSource = "context_menu";
      },
      args: [info.selectionText],
    });
    // Inject the content script
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    console.error("Recruiter Quick Search: context menu injection failed.", err);
  }
});

// Toolbar click + keyboard shortcut (Ctrl+Shift+Y) — fires via _execute_action
chrome.action.onClicked.addListener(async (tab) => {
  try {
    // Mark source as shortcut so content.js knows to use getSelection
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        window.__rqsSource = "shortcut";
      },
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    console.error("Recruiter Quick Search: cannot inject into this page.", err);
  }
});
