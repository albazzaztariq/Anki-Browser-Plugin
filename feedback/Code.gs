/**
 * AJS Bug Report → GitHub Issues
 * Google Apps Script — paste this into script.google.com
 *
 * Form fields (in order):
 *   0  Short description   (short answer)
 *   1  What happened?      (paragraph)
 *   2  Expected behaviour  (paragraph)
 *   3  OS                  (multiple choice: Windows / macOS)
 *   4  Anki version        (short answer)
 *   5  Steps to reproduce  (paragraph)
 *   6  Email (optional)    (short answer)
 */

var REPO  = "albazzaztariq/anki-japanese-sensei";
var LABEL = "user-report";

function onFormSubmit(e) {
  var r = e.response.getItemResponses();

  function get(i) {
    return r[i] ? String(r[i].getResponse()).trim() : "";
  }

  var title = get(0) || "Bug report (no title)";
  var email = get(6);

  var body = [
    "## What happened",
    get(1) || "_not provided_",
    "",
    "## Expected behaviour",
    get(2) || "_not provided_",
    "",
    "## Steps to reproduce",
    get(5) || "_not provided_",
    "",
    "## Environment",
    "- **OS:** " + (get(3) || "_not provided_"),
    "- **Anki version:** " + (get(4) || "_not provided_"),
    "",
    email ? ("---\n_Reported by: " + email + "_") : "",
  ].join("\n").trim();

  var token = PropertiesService.getScriptProperties()
                               .getProperty("GITHUB_TOKEN");
  if (!token) {
    Logger.log("ERROR: GITHUB_TOKEN not set in Script Properties.");
    return;
  }

  var response = UrlFetchApp.fetch(
    "https://api.github.com/repos/" + REPO + "/issues",
    {
      method:             "post",
      muteHttpExceptions: true,
      headers: {
        "Authorization": "token " + token,
        "Content-Type":  "application/json",
        "Accept":        "application/vnd.github+json",
      },
      payload: JSON.stringify({
        title:  "[User] " + title,
        body:   body,
        labels: [LABEL],
      }),
    }
  );

  var code = response.getResponseCode();
  Logger.log("GitHub API response: " + code + " — " + response.getContentText());
}
