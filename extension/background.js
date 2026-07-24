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
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    console.error("Recruiter Quick Search: cannot inject into this page.", err);
  }
});
