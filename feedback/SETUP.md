# Bug Report Form Setup

## 1. Create the Google Form

Go to forms.google.com → Blank form.  Add these fields **in this exact order**:

| # | Question | Type |
|---|----------|------|
| 0 | Short description of the problem | Short answer |
| 1 | What happened? | Paragraph |
| 2 | What did you expect to happen? | Paragraph |
| 3 | Operating system | Multiple choice → Windows / macOS |
| 4 | Anki version (Help → About) | Short answer |
| 5 | Steps to reproduce | Paragraph |
| 6 | Your email (optional, only if you want a reply) | Short answer |

Title the form: **Anki Japanese Sensei — Bug Report**

## 2. Attach the Apps Script

Inside the form: click the three-dot menu (⋮) → **Script editor**.

Delete any existing code and paste the contents of `Code.gs`.

## 3. Set your GitHub token

In the Script editor: **Project Settings** (gear icon) → **Script Properties** → Add property:

| Property | Value |
|----------|-------|
| `GITHUB_TOKEN` | your GitHub personal access token |

Generate the token at: github.com/settings/tokens
- Scope needed: `repo` (or just `public_repo` if the repo is public)
- Never paste the token anywhere else — it lives only in Script Properties

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
- GitHub repo → Issues — should have a new `[User] ...` issue with the `user-report` label

## 6. Add the link

Copy the form's shareable link and add it to:
- `README.md` — "Found a bug? Report it here: [link]"
- Installer completion screen (`installer/installer.py` — the final message)
