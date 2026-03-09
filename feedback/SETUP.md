# Bug Report Form Setup

## 1. Create the Google Form

Go to forms.google.com → Blank form.  Add these fields **in this exact order**:

| # | Question | Type |
|---|----------|------|
| 0 | Short description of the problem | Short answer |
| 1 | What happened? | Paragraph |
| 2 | What did you expect to happen? | Paragraph |
| 3 | Operating system | Multiple choice → Windows / macOS / Linux |
| 4 | Anki version (Help → About) | Short answer |
| 5 | Steps to reproduce | Paragraph |
| 6 | Your email (optional — only if you want a reply) | Short answer |
| 7 | AJS version (shown in Anki Tools → Japanese Sensei → Help) | Short answer |
| 8 | Browser | Multiple choice → Chrome / Edge / Other |

Title the form: **Anki Japanese Sensei — Bug Report**

## 2. Attach the Apps Script

Inside the form: click the three-dot menu (⋮) → **Script editor**.

Delete any existing code and paste the contents of `Code.gs`.

## 3. Set your GitHub token

The script needs a **fine-grained Personal Access Token** scoped only to Issues on this repo.
This is safer than a classic PAT — if it leaks, it can only create issues.

**Generate the token:**
1. Go to: github.com/settings/personal-access-tokens/new
2. Token name: `AJS Form → GitHub Issues`
3. Repository access: **Only selected repositories** → `Anki-Browser-Plugin`
4. Permissions: **Issues** → Read and Write
5. Generate and copy the token

**Add it to the script:**
In the Script editor: **Project Settings** (gear icon) → **Script Properties** → Add property:

| Property | Value |
|----------|-------|
| `GITHUB_TOKEN` | your fine-grained PAT (starts with `github_pat_`) |

Never paste this token anywhere else — Script Properties are encrypted at rest.

## 4. Set up the trigger

In the Script editor: **Triggers** (clock icon) → **+ Add Trigger**:

| Setting | Value |
|---------|-------|
| Function to run | `onFormSubmit` |
| Event source | From form |
| Event type | On form submit |

Save. Google will ask you to authorise the script — approve it.

## 5. Test it

Submit a test response through the form.  Check:
- Script editor → **Executions** — should show a successful run
- GitHub repo → Issues — should have a new `[User] ...` issue labelled `bug` + `user-report`

If the issue fails to file, the script emails you the failed payload automatically.

## 6. Get the shareable form URL

Forms → Share (send icon, top right) → Copy link.

Example: `https://docs.google.com/forms/d/e/LONG_ID/viewform`

## 7. Add the form URL to the codebase

Once you have the URL, add it in two places:

**`ajs_addon/config.py`:**
```python
FEEDBACK_FORM_URL: str = "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform"
```

**`terminal/config.py`:**
```python
FEEDBACK_FORM_URL: str = "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform"
```

This lets the in-app crash reporter and the Anki add-on's Report Bug button open the form
automatically as a fallback when automated GitHub filing isn't available.

## 8. Add the link to README

In `README.md`, update the "Found a bug?" line:
```
Found a bug? → [Submit a report](https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform)
```

Also add to the installer completion screen (`installer/installer.py` — the final print message).
