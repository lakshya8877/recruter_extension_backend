// Both icon click and Ctrl+Shift+Y fire chrome.action.onClicked
// because manifest.json uses "_execute_action" as the command.
chrome.action.onClicked.addListener(async (tab) => {
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    // Tabs like chrome://, edge://, or the extensions page block injection.
    console.error("Recruiter Quick Search: cannot inject into this page.", err);
  }
});
