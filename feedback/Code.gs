/**
 * AJS Bug Report → GitHub Issues
 * Google Apps Script — paste this into script.google.com
 *
 * Form fields (in order):
 *   0  Short description        (short answer)
 *   1  What happened?           (paragraph)
 *   2  Expected behaviour       (paragraph)
 *   3  OS                       (multiple choice: Windows / macOS / Linux)
 *   4  Anki version             (short answer)
 *   5  Steps to reproduce       (paragraph)
 *   6  Email (optional)         (short answer)
 *   7  AJS version              (short answer)
 *   8  Browser                  (multiple choice: Chrome / Edge / Other)
 */

var REPO   = "albazzaztariq/Anki-Browser-Plugin";
var LABELS = ["bug", "user-report"];

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
    "- **OS:** "           + (get(3) || "_not provided_"),
    "- **Anki version:** " + (get(4) || "_not provided_"),
    "- **AJS version:** "  + (get(7) || "_not provided_"),
    "- **Browser:** "      + (get(8) || "_not provided_"),
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
        "Authorization": "Bearer " + token,
        "Content-Type":  "application/json",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      payload: JSON.stringify({
        title:  "[User] " + title,
        body:   body,
        labels: LABELS,
      }),
    }
  );

  var code = response.getResponseCode();
  Logger.log("GitHub API response: " + code + " — " + response.getContentText());

  if (code !== 201) {
    // Send yourself a notification email if the issue failed to file.
    MailApp.sendEmail(
      Session.getEffectiveUser().getEmail(),
      "[AJS] Bug report failed to file on GitHub",
      "Response code: " + code + "\n\n" + response.getContentText() + "\n\nOriginal body:\n" + body
    );
  }
}
