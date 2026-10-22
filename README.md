# EmailOrbit — AI-Powered Personal Email Organizer

Final-year project. Built phase by phase — see project docs for the full
development plan. This README is updated as each phase lands.

### Compose, reply, attachments and Gmail drafts

Open **Compose** in the sidebar or **Reply** on an email (including the reading
pane). Plain-text messages support To/CC/BCC and up to ten attachments totalling
10 MB. Preview shows all recipients and file names before delivery. Replies use
the original Message-ID, References and Gmail thread ID; the reply subject is
kept fixed. Smart reply suggestions can be inserted and edited in the composer.
The preview's local completeness check highlights explicit requests with keyword
hints; it is advisory, not proof that a reply answers the questions correctly.

The existing Google login and normal **Connect Gmail** remain minimal/read-only.
From a message preview choose **Enable Gmail sending** to request `gmail.send`,
or **Enable Gmail drafts** to request `gmail.compose` (draft management also
permits sending). Both retain read access. Consent validates the same Google
account and returns to the saved preview without sending. If Google requests
consent-screen configuration, add the relevant scope to the existing Cloud
project's Google Auth Platform / Data Access settings. No new client secret or
redirect URI is required. Real send/draft tests must be completed in the browser
with the appropriate Google consent; automated tests mock Gmail and send nothing.

**Send email now** requires a checked review confirmation and CSRF validation.
**Save draft to Gmail** explicitly saves a remote draft without sending it.
Saved drafts and local previews appear in Compose's outgoing history; editing
preserves attachments unless you uncheck the option. Editing a Gmail draft uses
its original draft ID when you save/send the replacement preview. Edits made
separately in Gmail are not imported into the local preview. Check Gmail before
sending a draft that may have been edited there.

Outgoing MIME (including attachment bytes) and content are retained in the local
database, like other email data; OAuth tokens remain separately encrypted.
Durable state transitions prevent double-click/replayed submissions from sending
the same preview twice. There are no automatic send retries. An uncertain network
result blocks resubmission and instructs you to inspect Gmail Sent/Drafts first.
A sent receipt creates a local Sent email so follow-up detection sees your reply.
Tracking update failures do not retry delivery. Sending does not mark unrelated
commitments complete. The required additive migration is `0006_outgoing_mail.py`:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
```

### Commitment Tracker and ML/NLP review tools

The sidebar's **Commitments** page tracks explicit promises and requests across
synced messages. New syncs create proposals; **Scan synced emails** backfills
existing messages without duplicating proposals or reopening completed tasks.
Each proposal includes the source sentence and email, suggested responsibility
(me/other), and any extracted deadline. Confirm, edit, complete or dismiss it.
Deadline changes stay separate until you explicitly confirm a replacement of an
active commitment in the same conversation. Open excludes passed deadlines and
expired interview events. Overdue and its dashboard count include active tasks
and expired proposals, with proposals explicitly labelled unconfirmed. Contextual
interview dates assume IST and are labelled as inferred; stored user-entered
deadlines take precedence. Completed/dismissed items stay in history. Tracker
forms use their own CSRF token.

Apply the additive schema migration before using this version:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
```

Email detail now includes **Key information** (overview, requests, restrictions,
and dates requiring confirmation), a conversation timeline, and category feature
contributions when the saved linear model supports them. These are extractive
highlights, not LLM interpretation or guaranteed complete thread understanding.
Negated/completed requests are excluded by supported patterns. Weekdays with
times and `due in 2 days` are supported; locale-ambiguous numeric dates such as
03/04 are left for clarification. Original tasks/reminders are not regenerated.
Dates in tracker edit forms are explicitly UTC. A missing time assumes 17:00.
Only synced messages can be considered; unseen replies cannot close commitments.

The historical category model has poor minority-class recall despite its high
weighted F1. Inspect it without modifying models:

```powershell
python -m ml.audit_models
```

Download a private CSV from the tracker via **Help improve classification**.
Labels are intentionally blank: manually label examples, keep independent
training and evaluation files, and remove any spreadsheet-protection apostrophe
added to formula-like text before using that text in ML. The download contains
up to 300 of the current account's latest synced messages, not a random sample.
Build a representative review set rather than assuming this sample is unbiased.

Train isolated candidates on reviewed data (no live model replacement):

```powershell
python -m ml.train_reviewed data/labeled/training.csv --task categorization --output models_store/candidates/reviewed/categorization
python -m ml.train_reviewed data/labeled/training.csv --task priority --output models_store/candidates/reviewed/priority
python -m ml.train_reviewed data/labeled/training.csv --task spam --output models_store/candidates/reviewed/spam
python -m ml.evaluate_reviewed data/labeled/heldout.csv --models-dir models_store/candidates/reviewed --task category
```

CSV columns: `subject,body,sender,category,priority,spam_label`. Category labels
must match UI options, priority HIGH/MEDIUM/LOW, spam 0/1. Candidate training
deduplicates cleaned text, rejects conflicting labels, requires at least ten
distinct examples per class (a minimum guard, not adequate proof of quality),
fits features on training data only, and selects balanced SVM/logistic models
by validation macro F1. Per-class recall is also reported. Existing output
folders and standard live-model directories are refused. No human-reviewed
dataset or improved real-world accuracy is claimed or fabricated. Independently
evaluate candidates before a separately reviewed promotion; no automatic
retraining/promotion is implemented.

**Database setup for this checkout:** use [migrations/README](migrations/README).
It includes a replacement Phase 11 baseline and the large-email column upgrade.
The historical phase-by-phase migration commands below are development notes;
do not run `flask db init` or recreate those revisions for this checkout.

**Google OAuth callback:** register the exact `GOOGLE_REDIRECT_URI` value
on the Google Web application client (for example,
`http://127.0.0.1:5000/auth/callback`). Login and Gmail connection share this
callback, with separate state validation. Use that hostname when opening the app.

### Review fixes and current controls

- **Older mail:** Sync Gmail checks the most recent 25 messages. After that,
  **Load older emails** follows Gmail's next page token, one batch per click.
  A refresh resets the paging position; Sync Gmail starts again at recent mail.
  Existing messages are checked for read-status changes without duplicating them.
- **Sender rules:** when correcting a category or priority on an email, select
  **Apply this correction to future emails from this sender** to create a rule
  for your account. The latest correction for that sender and field wins.
  Submit a correction with the box unchecked to stop applying that rule to
  future emails. This is an explicit override, not model retraining; old messages
  are not automatically changed.
- **Deadlines and follow-ups:** common quoted replies are excluded from new
  request extraction. Relative dates use the email's Date timezone when present,
  with deadlines stored in UTC. Without a Date offset, the received timestamp is
  used. Unspecified times assume 17:00; ambiguous language still needs review.
- **Model compatibility:** requirements pin scikit-learn to 1.8.0 to match the
  shipped artifacts. Restart Flask after reinstalling requirements.

### Evaluate against human judgments

Create a separate UTF-8 CSV containing `subject,body,sender,category,priority,spam_label`
columns. Fill labels from independent human review; blank labels are skipped.
Priority labels are HIGH/MEDIUM/LOW and spam labels are 0/1. Do not use examples
from training or model tuning. Then run:

```powershell
python -m ml.evaluate_reviewed data/labeled/reviewed.csv
```

The command reports accuracy and macro F1 without training or changing saved
models. There is no human-labeled evaluation CSV in this checkout, so no new
real-world accuracy claim is made. The automatic categorizer still has only
Work/Personal/Other; broader category support requires suitable labeled data and
retraining. Sender rules can apply any category offered by the correction UI.

## Phase 1: Project setup + Flask + MySQL + SQLAlchemy

### Setup

```bash
cd emailorbit
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set SECRET_KEY, DB_USER, DB_PASSWORD, DB_NAME
```

Create the MySQL database (adjust user/password to match your `.env`):

```sql
CREATE DATABASE emailorbit CHARACTER SET utf8mb4;
CREATE USER 'emailorbit_user'@'localhost' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON emailorbit.* TO 'emailorbit_user'@'localhost';
FLUSH PRIVILEGES;
```

Initialize and apply the database migration:

```bash
export FLASK_APP=run.py
flask db init
flask db migrate -m "Phase 1: initial schema (users, emails, actions, reminders, user_feedback)"
flask db upgrade
```

Run the app:

```bash
python run.py
```

### Verify it works

```bash
curl http://localhost:5000/
curl http://localhost:5000/health
```

`/` should return `{"app": "EmailOrbit", "status": "running", "phase": "1 - project setup"}`.
`/health` should return `{"database": "connected"}`.

Run the automated tests:

```bash
pytest tests/test_setup.py -v
```

## Phase 2: Google OAuth authentication

### Google Cloud Console setup (one-time)

1. Go to console.cloud.google.com -> create/select a project.
2. APIs & Services -> OAuth consent screen -> External (or Internal if using
   Workspace) -> fill in app name/support email. Add your own email as a
   test user while the app is unpublished.
3. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   -> Application type: Web application.
   - Authorized redirect URI: `http://localhost:5000/auth/callback`
4. Copy the generated Client ID and Client Secret into `.env`:
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.

Do not download/commit the `credentials.json` file Google offers — this
app reads the client ID/secret from `.env` instead (see `app/blueprints/auth/oauth.py`).

### Local setup

Generate an encryption key for storing OAuth tokens at rest, and add it to `.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `ENCRYPTION_KEY=<that value>` and `OAUTHLIB_INSECURE_TRANSPORT=1` in `.env`
(the latter is only needed because local dev uses plain HTTP; never set it
in production).

Install the new dependencies and re-run migrations (OAuth token columns
already exist on `User` from Phase 1, so no schema change is needed):

```bash
pip install -r requirements.txt
python run.py
```

### Manual test (real Google login)

1. Open `http://localhost:5000/auth/login` in a browser.
2. You'll be redirected to Google's consent screen, asking only for your
   name/email/profile (no Gmail access yet — that's Phase 3).
3. After approving, you land back on `/auth/callback` with a JSON response
   confirming login and your user id/email.
4. Visit `http://localhost:5000/auth/me` — should show your profile.
5. Visit `http://localhost:5000/auth/logout`, then `/auth/me` again — should
   now return 401.

### Automated tests

```bash
pytest tests/test_auth.py -v
```

These cover the OAuth plumbing (state/CSRF checks, missing-code handling,
token encryption roundtrip, minimal-scope enforcement, login-required
guarding) without hitting Google's servers — the real end-to-end login is
the manual test above.

## Phase 3: Gmail API integration and email synchronization

### What this adds

A new `gmail` blueprint that:
- requests the `gmail.readonly` scope **incrementally** — on top of, not
  instead of, the Phase 2 login scopes, and only once the user explicitly
  chooses to connect Gmail (rule #16)
- fetches recent message ids + full message resources via the Gmail API
- stores one `Email` row per Gmail message, keyed by `gmail_message_id` so
  re-syncing never creates duplicates (rule #13)
- refreshes an expired access token automatically using the stored
  refresh token, persisting the new one back to the (encrypted) column
- does **not** decode the MIME body yet — that's Phase 4. The raw Gmail
  message resource is stashed in `Email.raw_payload` so the parser can
  work from it without re-fetching from Gmail

### Update your database schema

Two columns were added (`User.gmail_scope_granted`, `Email.raw_payload`):

```bash
flask db migrate -m "Phase 3: gmail connection + raw payload staging"
flask db upgrade
```

### Update your Google Cloud OAuth consent screen

Add the Gmail read-only scope to your OAuth consent screen configuration
(APIs & Services -> OAuth consent screen -> Scopes) if prompted:
`https://www.googleapis.com/auth/gmail.readonly`. You'll also need the
Gmail API enabled for your project (APIs & Services -> Library -> Gmail API -> Enable).

### Manual test (real Gmail account)

1. Log in first via `/auth/login` (Phase 2).
2. Visit `http://localhost:5000/gmail/connect` — consent screen now also
   asks for read-only Gmail access.
3. After approving, `/gmail/callback` should return
   `{"message": "Gmail connected successfully"}`.
4. Trigger a sync:
   ```bash
   curl -X POST "http://localhost:5000/gmail/sync?max_results=10" \
        -H "Cookie: session=<copy from browser dev tools>"
   ```
   (or just hit it from a tool like Postman/Insomnia using the same
   logged-in browser session). Response looks like:
   `{"total_fetched": 10, "synced": 10, "skipped_existing": 0}`.
5. Run it again — `synced` should now be `0` and `skipped_existing` should
   equal the previous `synced` count, proving dedup works.

### Automated tests

```bash
pytest tests/test_gmail_sync.py -v
```

These fake out the Gmail API entirely (an in-memory stub standing in for
`service.users().messages()`), so they run without any real Google
credentials or network access — verifying header extraction, dedup on
re-sync, raw payload staging, incremental-scope requests, and the
gmail-not-connected error path.

## Phase 4: Email parser + database storage

### What this adds

- `app/blueprints/emails/parser.py` — decodes a Gmail message's MIME body
  (`Email.raw_payload` from Phase 3) into clean plain text: walks
  multipart/alternative and multipart/mixed structures, prefers text/plain
  parts, falls back to stripping HTML down to text when only an HTML part
  exists, and skips attachments (parts with no inline body data) entirely.
- `sync_user_emails()` (Phase 3) now calls this parser during sync, so
  newly synced emails get a populated `body` field immediately — no
  separate "run the parser" step is needed.
- `app/blueprints/emails/` — a new JSON API:
  - `GET /emails` — paginated, filterable (`is_read`, `category`,
    `priority`) inbox list, ordered newest first, snippet-only (no full
    body) to keep list responses small
  - `GET /emails/<id>` — full detail for one email, including body
  - `PATCH /emails/<id>/read` — mark read/unread
  
  Every route scopes to `session['user_id']`; requesting another user's
  email id returns 404, never their data (rule #17).

### Update your database schema

No new columns this phase — `body` already existed on `Email` since
Phase 1, it's just populated now. If you're starting fresh, run:

```bash
flask db upgrade
```

### Manual test (real Gmail account)

1. Log in and connect Gmail (Phases 2-3), then `POST /gmail/sync`.
2. `GET /emails` — you should see real subjects/snippets from your inbox.
3. `GET /emails/<id>` for one of the ids from step 2 — `body` should be
   readable plain text, even for HTML-only marketing emails.
4. `PATCH /emails/<id>/read` with `{"is_read": true}` — re-fetch the list
   with `?is_read=false` and confirm that email no longer appears.

### Automated tests

```bash
pytest tests/test_email_parser.py tests/test_emails_api.py -v
```

`test_email_parser.py` covers plain-text, HTML-fallback, nested
multipart, and attachment-skipping cases directly against the parser.
`test_emails_api.py` covers pagination validation, snippet truncation,
and — importantly — that one user can never read or modify another
user's email via the JSON API.

## Phase 6: ML datasets + preprocessing + training

**Training happens offline, outside the Flask app (rules #3/#14/#15) —
these scripts are run from the command line, produce `.joblib` model
files under `models_store/`, and Phase 7's Flask blueprint will only ever
load those files, never retrain them.**

### Datasets used

- **Categorization**: `data/raw/enron/enron_with_categories/` — the
  Berkeley-labeled Enron subset (each email is a `<id>.txt` + `<id>.cats`
  pair across 8 folders).
- **Spam detection**: `data/raw/spamassassin/` — `20030228_easy_ham/`,
  `20030228_hard_ham/`, `20030228_spam/` (the standard public corpus
  layout; `_2` variants are picked up automatically if present).
- **Priority detection**: no separate download — pseudo-labels (HIGH/
  MEDIUM/LOW) are derived from the same Enron corpus using a documented,
  transparent heuristic (urgency keywords, deadline phrases, sender
  domain, etc. — see `ml/priority_detection/feature_engineering.py`).

### Important scope note on categorization

The Enron corpus's `.cats` files label emails against an academic
taxonomy (Company Business / Personal / Logistics / Employment /
Document-editing / Empty-message), not EmailOrbit's 9-category list.
Enron is corporate operational email — it has essentially zero real
Finance, Shopping, Travel, Social, or Promotions examples. Rather than
forcing a 9-way classifier to guess at categories it never saw a single
real example of, **Phase 6 trains categorization on the 3 categories the
data actually supports: Work, Personal, Other.** This was a deliberate,
documented decision (confirmed with the project owner) — write it up as
a dataset limitation in your report, not a shortcut you're hiding.

### Run it

```bash
pip install -r requirements.txt   # adds scikit-learn, pandas, numpy, scipy, joblib, matplotlib

python -m ml.categorization.preprocess
python -m ml.categorization.train
python -m ml.categorization.evaluate      # optional — prints a full report per model

python -m ml.spam_detection.preprocess
python -m ml.spam_detection.train
python -m ml.spam_detection.evaluate

python -m ml.priority_detection.preprocess
python -m ml.priority_detection.train
python -m ml.priority_detection.evaluate
```

Each `train.py`:
- splits 80/20 (stratified, `random_state=42` so `evaluate.py` can
  reproduce the identical split without saving it separately)
- fits TF-IDF (categorization/spam) or TF-IDF + engineered numeric
  features combined (priority)
- trains and compares Logistic Regression, Linear SVM, and Naive Bayes
  (Random Forest instead of Naive Bayes for priority — a better fit for
  mixed text+numeric features, see `ml/priority_detection/train.py`'s
  docstring)
- reports accuracy/precision/recall/F1 (weighted) + a confusion matrix
  PNG per model, all saved under `models_store/<task>/`
- saves every model + vectorizer individually (so results are
  inspectable/reproducible), then copies whichever won on weighted F1 to
  fixed `production_model.joblib` / `production_vectorizer.joblib`
  filenames — this is what Phase 7's inference code will load, so it
  never needs to know which algorithm happened to win

`models_store/<task>/metrics.json` has the full comparison — pull
numbers/plots from there for your report.

### A bug I actually caught while verifying this

I ran the full pipeline against small, format-accurate synthetic data
before handing it to you (mimicking your real `.txt`/`.cats` and
SpamAssassin file structures) and hit a real crash: spam detection's
labels are `0`/`1` (numpy integers from pandas), and `json.dump()` can't
serialize numpy's integer/float types — it works for categorization
(string labels) but broke on spam's numeric ones. Fixed in
`ml/common/dataset_utils.py` with a recursive native-type converter
before every JSON write. Worth knowing since it's the kind of bug that
only shows up once you actually run the numeric-label pipeline, not the
string-label one.

### Automated verification

There isn't a `pytest` suite for this phase — training against real
Enron/SpamAssassin data takes real time and belongs on your machine, not
mocked in CI. Verification here means: I ran the full
preprocess→train→evaluate pipeline for all three tasks against small
synthetic data built from your **actual file formats** (confirmed by
reading real files from your connected folder) and fixed the bug above.
When you run it for real, check that `models_store/<task>/metrics.json`
exists and that the confusion matrix PNGs look sane for your data size.

## Phase 5: Inbox + dashboard UI

### What this adds

Server-rendered HTML pages (Bootstrap 5 + vanilla JS + Chart.js), all
served by the `dashboard` blueprint so that `auth`/`gmail`/`emails` stay
pure JSON APIs consumed by these pages' own `fetch()` calls:

- `GET /` — landing page (public). Shows a "Continue with Google" button
  if not logged in; redirects straight to `/dashboard` if already logged in.
- `GET /dashboard` — stat cards (total/unread/high-priority emails,
  pending replies, upcoming deadlines — the latter two report `0` until
  Phases 8-10 populate them), a Chart.js category-breakdown doughnut
  chart, and a Sync Gmail button (or Connect Gmail, if not yet connected).
- `GET /dashboard/stats` — the JSON endpoint the dashboard's JS reads
  (counts + category breakdown), scoped to the logged-in user only.
- `GET /inbox` — paginated inbox list with a read/unread filter; each row
  links to its detail page. Calls the Phase 4 `/emails` API under the hood.
- `GET /inbox/<id>` — full email view (sender/receiver/timestamp, category
  and priority badges — shown as "pending" until Phase 7's ML models run
  — summary placeholder, full body, mark read/unread button).

`app/templates/` holds the Jinja templates (`base.html` + one per page);
`app/static/css/style.css` and `app/static/js/*.js` hold the small amount
of custom styling/behavior on top of Bootstrap. `/auth/callback`,
`/gmail/callback`, and `/auth/logout` now redirect into these pages
(with a flashed message) instead of returning raw JSON, since a human is
the one hitting them via the browser.

### Update your database schema

No schema changes this phase — everything rendered here already existed
in the database (Phases 1-4).

### Manual test (in a browser)

1. Visit `http://localhost:5000/` — you should see the landing page with
   a "Continue with Google" button.
2. Log in (Phase 2), connect Gmail (Phase 3) from the dashboard's
   "Connect Gmail" button, then click "Sync Gmail".
3. The stat cards and category chart should update after syncing.
4. Go to Inbox, confirm your synced emails show up with sender/subject/
   snippet, and that the Unread/Read filter actually filters the list.
5. Click an email — you should land on its detail page with the full
   parsed body, and "Mark as Read"/"Mark as Unread" should toggle live
   without a page reload.
6. Log out — you should land back on the public landing page.

### Automated tests

```bash
pytest tests/test_dashboard_ui.py -v
```

These render every page (landing, dashboard, inbox list, inbox detail)
through Flask's test client and check: login is required where it should
be, stats are correctly scoped to the logged-in user only (a second
user's emails never leak into the first user's counts), null categories
are grouped as "Uncategorized" rather than crashing the chart, and that
opening another user's email by id redirects away instead of rendering
it (rule #17, enforced at the page layer too, not just the JSON API).

## Phase 7: Categorization + spam + priority inference

### What this adds

Wires the three models trained in Phase 6 into live inference, following
rule #14 (load pre-trained models, never train during a web request):

- `app/blueprints/ml_inference/predictors.py` — loads each task's
  `production_model.joblib` (+ `production_vectorizer.joblib`, and for
  priority also `production_scaler.joblib`) from `MODELS_DIR`
  (`models_store/<task>/`, configurable via the `MODELS_DIR` env var),
  caching them in memory after the first load so a request never touches
  disk twice. `predict_category(text)`, `predict_spam(text)`, and
  `predict_priority(subject, body, sender)` each return a
  `(label, confidence)` pair. Confidence is extracted the same way
  regardless of which algorithm won during Phase 6's train/compare step:
  `predict_proba` when the model has it (Logistic Regression, Naive
  Bayes), otherwise `decision_function` (LinearSVC) — sigmoid-normalized
  for a binary task, softmax-normalized across one-vs-rest scores for a
  multiclass task. Priority prediction reuses `FEATURE_COLUMNS` and
  `extract_features()` straight from `ml/priority_detection/` (rather
  than redefining them here) so the features seen at inference time can
  never drift from the ones the model was trained on. If a task's model
  files aren't present yet, these functions raise `ModelNotTrainedError`
  instead of crashing.
- `app/blueprints/ml_inference/classifier.py` — `classify_email(email)`
  bridges the three predictors to an `Email` row: sets
  `category`/`category_confidence`, `spam_label`/`spam_probability`,
  `priority`/`priority_confidence`. Catches `ModelNotTrainedError`
  per-field, so if you've only trained (say) categorization so far, spam
  and priority just stay `None` rather than blocking the whole sync.
  Doesn't commit — the caller decides when.
- `app/blueprints/gmail/sync_service.py` — now calls `classify_email()`
  on every newly-synced email before it's added to the session, so
  classification happens automatically as part of `Sync Gmail`.
- `app/blueprints/ml_inference/routes.py` — JSON API for on-demand /
  backfill classification (e.g. for emails synced before these models
  existed, or after retraining with more data):
  - `POST /ml/classify/<email_id>` — reclassify one email now.
  - `POST /ml/classify-all` — classify every email for the logged-in
    user that doesn't have a category yet.
  Both return `503` with a clear message if no trained models are found
  at all, rather than a silent no-op or a stack trace.
- `app/config.py` — added `MODELS_DIR`, pointing at `models_store/` by
  default (overridable via env var), so the app and the Phase 6 training
  scripts agree on where models live without hardcoding a path twice.

### Update your database schema

No schema changes — `category`, `category_confidence`, `spam_label`,
`spam_probability`, `priority`, and `priority_confidence` columns on
`Email` already existed from earlier phases; this is the first phase
that actually writes to them.

### Run it

Make sure Phase 6's training has produced `models_store/categorization/`,
`models_store/spam/`, and `models_store/priority/`, each with a
`production_model.joblib` (categorization/spam also need
`production_vectorizer.joblib`; priority also needs
`production_vectorizer.joblib` and `production_scaler.joblib`).

```bash
flask run
```

Then either sync Gmail again (new emails get classified automatically),
or backfill anything already in your inbox:

```bash
curl -X POST http://localhost:5000/ml/classify-all \
  -H "Cookie: session=<your session cookie>"
```

(or just click through the browser while logged in — any `POST` to that
URL works, including one wired up to a button in a later UI pass).

### Automated tests

```bash
pytest tests/test_ml_inference.py -v
```

Real trained models aren't guaranteed to exist in every environment
(they come from running Phase 6 against your real datasets), so these
tests avoid depending on one: `_predict_with_confidence` is tested
against small hand-built mock estimators that mimic sklearn's
`predict_proba`/`decision_function` interface (covering the
probability, binary-decision, and multiclass-decision cases separately),
`ModelNotTrainedError` is confirmed to raise cleanly against an empty
models directory, `classify_email()`'s field-wiring and partial-model
survival are tested with the real predictors monkeypatched out, and the
`/ml/classify/*` routes are tested end-to-end (login required, 404 on
another user's email, 503 when nothing is trained, 200 with the email's
new fields on success, and that `/ml/classify-all` skips emails that
already have a category).

```bash
pytest tests/ -v
```

All 60 tests (49 from Phases 1-5 + 11 new here) pass together.

## Phase 8: Summarization + action-item extraction + deadline detection

### What this adds

Three independent, dependency-light NLP features, each a pure text-in
text-out function first (no DB, no Flask), then wired into the app by a
thin service layer — same split as Phase 7's ML blueprint:

- `app/blueprints/nlp_features/summarizer.py` — `summarize_text(text,
  max_sentences=3)`. Classic frequency-based **extractive** summarization:
  no transformer model, no external API call, no training step (rules
  #3/#14/#15) — it scores every sentence by how many frequent,
  non-stopword words it contains, and keeps the top-scoring sentences in
  their original order. Returns the text unchanged if it's already
  short enough to not need summarizing.
- `app/blueprints/nlp_features/action_extractor.py` —
  `extract_action_items(text, max_items=5)`. Rule-based: splits into
  sentences and flags ones matching request patterns (`please`,
  `kindly`, `can/could/would you`, `need(s) to`, `action item/required`,
  etc.) or that open with an imperative verb (`Send the file...`,
  `Review this...`). Transparent and instantly explainable in a project
  report, at the cost of some recall versus a trained classifier.
- `app/blueprints/nlp_features/deadline_extractor.py` —
  `extract_deadlines(text, reference_time=None)`. Finds date phrases
  following trigger words (`by`, `due`, `deadline`, `before`, `no later
  than`, `until`), normalizes informal/relative phrasing by hand first
  (`tomorrow`, `EOD`/`end of day`/`COB`, `next Monday`, a bare weekday
  name) since `dateutil.parser` has no idea what those mean, then falls
  back to `dateutil.parser.parse(fuzzy=True)` for explicit dates
  ("March 15, 2027"). `reference_time` is a parameter (not
  `datetime.now()` baked in) specifically so tests can assert against a
  fixed date instead of "whatever day the test happens to run."
- `app/blueprints/nlp_features/service.py` — `process_email_nlp(email)`
  is the only place that touches the DB: sets `Email.summary`, and
  appends new `Action`/`Reminder` rows onto the email's relationships
  for whatever the extractors found. Mirrors Phase 7's
  `classify_email()` — mutates in place, doesn't commit, callers decide
  when.
- `app/blueprints/gmail/sync_service.py` — calls `process_email_nlp()`
  right after `classify_email()` for every newly-synced email, so
  summaries/actions/deadlines appear automatically on sync.
- `app/blueprints/nlp_features/routes.py` — `POST /nlp/process/<id>`
  (reprocess one email) and `POST /nlp/process-all` (backfill every
  email that doesn't have a summary yet), both scoped to the logged-in
  user (rule #17).
- `app/blueprints/emails/serializers.py` — `to_detail_dict()` now
  includes `actions` and `reminders` lists alongside the existing
  fields.
- `app/templates/emails/email_detail.html` — the inbox detail page now
  renders the summary (replacing the "pending" placeholder from Phase
  5), plus an Action Items list and a Deadlines list when the email has
  any.
- `requirements.txt` — added `python-dateutil` (imported directly now,
  rather than relying on it being present transitively via pandas).

Follow-up detection, duplicate detection, and the dashboard's "pending
replies" stat are still Phase 10. The dashboard's "upcoming deadlines"
stat card (Phase 5) already queried the `Reminder` table, so it starts
reflecting real numbers as soon as emails get processed here — no
dashboard code changed this phase.

### Update your database schema

No schema changes — `Email.summary`, the `actions` table, and the
`reminders` table were already defined in the Phase 1 models (scaffolded
ahead of time for this phase); this is just the first phase that writes
to them. If you're starting fresh:

```bash
flask db upgrade
```

### Install the new dependency

```bash
pip install -r requirements.txt
```

### Run it

```bash
flask run
```

Sync Gmail again (new emails get processed automatically), or backfill
anything already in your inbox:

```bash
curl -X POST http://localhost:5000/nlp/process-all \
  -H "Cookie: session=<your session cookie>"
```

Then open an email's detail page — you should see a real summary, and
an Action Items / Deadlines section if the email contained any.

### Automated tests

```bash
pytest tests/test_nlp_features.py -v
```

The summarizer, action extractor, and deadline extractor are each
tested directly against hand-written email text with no DB involved
(including that the summarizer favors on-topic sentences over filler,
the action extractor ignores plain statements and a negated "no action
needed" sentence, and the deadline extractor correctly resolves
`tomorrow`/`EOD`/`next Monday`/explicit dates against a fixed
`reference_time` rather than the real "now"). `process_email_nlp()`'s
DB wiring and the `/nlp/process/*` routes are tested the same way as
Phase 7 (login required, cross-user 404, backfill skips already-
processed emails).

```bash
pytest tests/ -v
```

All 80 tests (60 from Phases 1-7 + 20 new here) pass together.

## Phase 9: Smart replies

### What this adds

Suggested quick-reply text on the inbox detail page, generated one of
two ways depending on configuration — a deliberate design choice (see
the project discussion this phase started from): a real LLM produces
noticeably better, more natural replies than rule-based templates, but
it means sending email content to a third-party API, real cost per
call, network latency/failure inside the sync pipeline, and non-
deterministic output that's harder to unit test. The compromise: use
the LLM when it's configured, and always have a free, offline,
deterministic fallback so the feature works with zero setup and never
breaks sync if the API key is missing, invalid, or rate-limited.

- `app/blueprints/smart_replies/llm_client.py` — calls the Anthropic API
  (`ANTHROPIC_API_KEY` / `SMART_REPLY_MODEL` in `.env`, defaults to
  `claude-3-5-haiku-latest`) with the email's subject/body/sender,
  asking for a small JSON array of short reply suggestions. Every
  failure mode — no key configured, network error, rate limit, a
  response that isn't clean JSON — is normalized into one
  `LLMUnavailableError` rather than letting a raw SDK/network exception
  escape.
- `app/blueprints/smart_replies/templates.py` — the fallback:
  `generate_template_replies(email)` scores a fixed pool of reply
  templates (acknowledge, confirm, request more info, will-review,
  deadline-acknowledge, too-busy-right-now) against signals already
  computed by earlier phases — does the email have a question mark, an
  extracted action item (Phase 8), a detected deadline (Phase 8), HIGH
  priority (Phase 7) — and returns the top-scoring ones. Same rule-based
  philosophy as Phase 8's action extractor: transparent, no training
  data, zero cost, always available.
- `app/blueprints/smart_replies/service.py` — `generate_smart_replies
  (email)` tries the LLM first, catches `LLMUnavailableError`, and falls
  back to templates on ANY failure. Sets `Email.smart_replies` (JSON-
  encoded list) and `Email.smart_reply_source` ("llm" or "template") so
  it's visible which path actually ran. Doesn't commit — caller's job.
- `app/blueprints/gmail/sync_service.py` — calls
  `generate_smart_replies()` for every newly-synced email that
  `classify_email()` didn't flag as spam (no point drafting replies to
  spam, and skipping it saves an LLM call).
- `app/blueprints/smart_replies/routes.py` — `POST
  /replies/generate/<id>` and `POST /replies/generate-all` (backfill
  emails without smart replies yet), same login/ownership rules as
  every other route.
- `app/models/email.py` — added `smart_replies` (`Text`, JSON-encoded
  list) and `smart_reply_source` (`String(16)`) columns.
- `app/blueprints/emails/serializers.py` — `to_detail_dict()` now
  decodes and includes `smart_replies`/`smart_reply_source`.
- `app/templates/emails/email_detail.html` +
  `app/static/js/email_detail.js` — renders each suggestion as a clickable
  chip; clicking copies its text to the clipboard (rule-appropriate
  scope: this app suggests replies, it doesn't send mail on your
  behalf — you paste the suggestion into Gmail's own reply box).
- `app/config.py` / `.env.example` — added `ANTHROPIC_API_KEY` (optional,
  never hardcoded) and `SMART_REPLY_MODEL`.
- `requirements.txt` — added `anthropic` (only actually called if a key
  is configured).

### Update your database schema

Two columns were added (`Email.smart_replies`, `Email.smart_reply_source`):

```bash
flask db migrate -m "Phase 9: smart reply suggestions"
flask db upgrade
```

### Configure the LLM (optional)

Leave `ANTHROPIC_API_KEY` blank in `.env` to use templates only — no
signup, no cost, works immediately. To get LLM-generated replies
instead, get a key from the Anthropic Console and set it:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SMART_REPLY_MODEL=claude-3-5-haiku-latest
```

### Install the new dependency

```bash
pip install -r requirements.txt
```

### Run it

```bash
flask run
```

Sync Gmail again (new non-spam emails get replies drafted
automatically), or backfill anything already in your inbox:

```bash
curl -X POST http://localhost:5000/replies/generate-all \
  -H "Cookie: session=<your session cookie>"
```

Open an email's detail page — you'll see up to 3 suggested reply chips
and a note on whether they came from the AI or the template fallback.

### Automated tests

```bash
pytest tests/test_smart_replies.py -v
```

None of these tests call the real Anthropic API or cost anything to
run: `llm_client.py` is tested against a hand-built fake client object
that mimics only the slice of the SDK's interface this code actually
calls (`client.messages.create(...).content[0].text`), covering clean
JSON parsing, markdown-code-fence stripping, an unparseable response,
and a simulated API error — all correctly raising
`LLMUnavailableError`. `templates.py` is tested directly against
hand-built fake email objects (question → request-info template,
detected deadline → deadline-ack template, etc.). `service.py`'s
LLM-first/template-fallback wiring and the `/replies/generate/*` routes
are tested with `generate_llm_replies` monkeypatched out (both a
success case and a simulated failure that should trigger the
template fallback).

```bash
pytest tests/ -v
```

All 95 tests (80 from Phases 1-8 + 15 new here) pass together.

## Phase 10: Follow-up detection + duplicate detection + personalization

### What this adds

Three features, wrapping up the "unique features" list from the
project spec. The first two are deliberately **batch** operations
rather than per-email steps during sync (unlike every AI/ML field set
so far) — detecting either one means comparing an email against OTHER
emails, including ones from the very same sync, which only gives a
correct answer once every new email is already committed:

- `app/blueprints/followup/detector.py` — pure signal functions:
  `needs_response(email)` (does it contain a question, an extracted
  action item from Phase 8, or HIGH/MEDIUM priority from Phase 7?) and
  `is_stale(email, reference_time=None, threshold_days=2)` (older than
  the threshold — `reference_time` is injectable, never
  `datetime.now()` baked in, so tests are deterministic).
- `app/blueprints/followup/service.py` — `detect_pending_follow_ups
  (user_id)` scans the user's whole mailbox, works out the last time
  the user themselves sent a message in each Gmail thread, and sets
  `Email.needs_follow_up` on every received, non-spam email that needs
  a response, is stale, AND has no later reply from the user in the
  same thread — clearing the flag the same way once a reply does show
  up.
- `app/blueprints/followup/routes.py` — `POST /followups/detect` for
  on-demand rechecking (also runs automatically at the end of every
  sync).
- `app/blueprints/deduplication/hashing.py` —
  `compute_content_hash(subject, body)`: a SHA-256 hash of normalized
  (lowercased, punctuation-stripped, whitespace-collapsed) text.
  Deliberately **exact**-match, not fuzzy — instant, no new dependency,
  trivial to test and explain, at the cost of missing near-duplicates
  that differ by a signature line. Worth stating as a scope limitation
  in the report, same as Phase 6's 3-class categorization decision.
- `app/blueprints/deduplication/service.py` —
  `detect_duplicate_emails(user_id)` groups a user's emails by content
  hash and flags every email except the earliest in each group as
  `is_duplicate=True`, pointing `duplicate_of_email_id` at that
  earliest email.
- `app/blueprints/deduplication/routes.py` — `POST /duplicates/detect`
  (also runs automatically at the end of every sync).
- `app/blueprints/gmail/sync_service.py` — calls both detectors once,
  after the per-message loop and its commit (not inside the loop),
  and now also returns `duplicates_found`/`needs_follow_up` counts.
- **Personalization**: `app/blueprints/emails/routes.py` — `POST
  /emails/<id>/feedback` records a `UserFeedback` row (category or
  priority correction — this model existed since Phase 1) AND applies
  the correction to the email immediately, rather than only feeding a
  future retrain that's out of this project's scope. `GET /emails` also
  gained `needs_follow_up`/`is_duplicate` filter params, matching the
  existing `is_read`/`category`/`priority` ones.
- `app/models/email.py` — added `needs_follow_up` (Boolean),
  `content_hash` (String, indexed), `is_duplicate` (Boolean),
  `duplicate_of_email_id` (Integer FK to `emails.id`).
- `app/blueprints/emails/serializers.py` — both dict shapes now include
  the new fields.
- `app/blueprints/dashboard/routes.py` — `pending_replies` (previously
  hardcoded to 0) now counts real `needs_follow_up` emails; added a new
  `duplicate_emails` stat.
- `app/templates/dashboard/dashboard.html` — added a Duplicate Emails
  stat card (the generic `data-stat` JS wiring from Phase 5 picks it up
  automatically, no JS changes needed).
- `app/templates/emails/inbox.html` + `app/static/js/inbox.js` — a
  "Needs Follow-up" filter dropdown, plus badges on each inbox row.
- `app/templates/emails/email_detail.html` +
  `app/static/js/email_detail.js` — follow-up/duplicate badges, a link
  to the original email when this one is a duplicate, and two dropdowns
  ("Correct category…" / "Correct priority…") that submit a correction
  on change.

### Update your database schema

Four columns were added to `Email`:

```bash
flask db migrate -m "Phase 10: follow-up + duplicate detection fields"
flask db upgrade
```

### Run it

```bash
flask run
```

Sync Gmail again — follow-up flags and duplicate flags are recomputed
automatically at the end of the sync. Or trigger either scan on demand:

```bash
curl -X POST http://localhost:5000/followups/detect  -H "Cookie: session=<...>"
curl -X POST http://localhost:5000/duplicates/detect  -H "Cookie: session=<...>"
```

Open the dashboard to see the new "Duplicate Emails" card and a real
"Pending Replies" count; open the inbox and filter by "Needs
Follow-up"; open an email that got miscategorized and use the "Correct
category…" dropdown — the category updates immediately and a
`UserFeedback` row is recorded.

### Automated tests

```bash
pytest tests/test_followup_and_dedup.py tests/test_feedback.py -v
```

`detector.py`'s `needs_response`/`is_stale` are tested directly against
hand-built fake email objects. `followup/service.py` is tested against
a real (SQLite) database: a stale unanswered question gets flagged, the
flag clears once a later same-thread reply from the user exists, and
spam is never flagged. `deduplication/hashing.py` is tested for
normalization-insensitive matching, different content producing
different hashes, and empty input returning `None`.
`deduplication/service.py` is tested for correctly flagging an exact
repeat (and not flagging genuinely distinct emails). The feedback route
is tested for login/ownership rules, input validation, and that a
correction is both recorded AND applied to the email immediately.

```bash
pytest tests/ -v
```

All 119 tests (95 from Phases 1-9 + 24 new here) pass together.

This closes out the feature list from the original project spec.
Deployment (Phase 12) is out of scope per project decision, so Phase 11
below — testing/evaluation — is the last phase.

## Phase 11: Testing and evaluation

Every earlier phase already shipped with its own pytest suite (rule
#20: every major feature independently testable), so this phase isn't
"start writing tests" — it's the two kinds of testing/evaluation that
don't belong to any single feature: proving the phases actually work
*together*, and consolidating the ML models' evaluation results into
one report for the project write-up. A small amount of dead-code
cleanup (three unused scaffold blueprint folders left over from Phase
1's original plan — `ai_features/`, `feedback/`, `insights/` — never
imported or registered anywhere once the real blueprints took shape
under different names) was also removed here.

### What this adds

- `tests/test_integration_pipeline.py` — an end-to-end test that trains
  tiny (but real, not mocked) scikit-learn models on the fly, points the
  app at them, fakes the Gmail API, and runs one real
  `sync_user_emails()` call — then asserts every phase's field actually
  landed on the resulting `Email` row: category/spam/priority (Phase
  7), summary/actions/reminders (Phase 8), smart replies via the
  template fallback (Phase 9), and follow-up/duplicate flags (Phase
  10). A second test proves duplicate detection catches two identical
  emails arriving in the *same* sync batch, not just across separate
  syncs — directly verifying the design choice explained in Phase 10's
  section (run the detector once after the whole batch commits, not
  per-message).
- `ml/evaluate_all.py` — reads all three tasks'
  `models_store/<task>/metrics.json` (produced by Phase 6's `train.py`
  scripts) and writes one consolidated comparison —
  `models_store/evaluation_summary.md` (paste straight into a project
  report) and `.json` (machine-readable). Reports every algorithm's
  accuracy/precision/recall/F1 side by side per task, marks the best
  model, and attaches the categorization/priority scope caveats
  automatically so they can't be accidentally left out of a report.
  A task with no `metrics.json` yet is reported as "not yet trained"
  rather than crashing the script.
- `tests/test_evaluate_all.py` — tests `evaluate_all.py` against small
  hand-built `metrics.json` fixtures in a temp directory (never touches
  the user's real `models_store/`): missing tasks are reported
  correctly, the best model is marked in the rendered Markdown, caveats
  attach to the right tasks, and both output files get written.
- `requirements.txt` — added `pytest-cov`, used for the coverage
  numbers below.

### Run it

```bash
pip install -r requirements.txt

# Consolidated ML evaluation report (needs at least one Phase 6 task trained):
python -m ml.evaluate_all
cat models_store/evaluation_summary.md

# Full test suite:
pytest tests/ -v

# With coverage:
pytest tests/ --cov=app --cov=ml --cov-report=term-missing
```

### Coverage results (this sandbox, synthetic Enron/SpamAssassin-shaped test data)

Overall: **64%** across `app/` + `ml/`. This isn't evenly distributed,
and that unevenness is expected rather than a gap to close:

- `app/blueprints/*/predictors.py`, `classifier.py`, `service.py`,
  `hashing.py`, `detector.py`, `serializers.py` (the actual AI/ML/NLP/
  personalization logic from Phases 7-10) — **96-100%**. This is the
  code whose correctness actually matters for the ML/AI claims in the
  project title, and it's the code every phase's own test suite targets
  directly.
- `ml/*/train.py`, `preprocess.py`, `evaluate.py`, `ml/common/
  dataset_utils.py` — **0-26%**. Deliberately untested by pytest, not
  missed: these run offline against real multi-hundred-MB datasets
  (rule #3/#15), take real minutes to run, and were verified instead by
  actually running them against real data during Phase 6 (see that
  phase's section above for the three bugs that verification caught).
  A unit test suite here would either need to fake the entire
  scikit-learn training pipeline (low value) or ship a slow integration
  test against real data (impractical for a CI-style `pytest tests/`
  run) — `ml/evaluate_all.py` and Phase 6's own real-data run are the
  actual verification for this code.
- `app/blueprints/auth/routes.py`, `gmail/routes.py`,
  `gmail/gmail_client.py` — **46-59%**. The parts that talk to Google's
  real OAuth/Gmail endpoints aren't exercised by tests that (correctly)
  avoid making real network calls or requiring real Google credentials;
  the parts that ARE tested (scope handling, state validation, dedup,
  error paths) are exactly the parts that don't need a live Google
  account to verify.

### Automated tests

```bash
pytest tests/test_integration_pipeline.py tests/test_evaluate_all.py -v
```

```bash
pytest tests/ -v
```

All 127 tests (119 from Phases 1-10 + 8 new here) pass together.

## Limitations and future work

Worth stating explicitly in a project report rather than leaving
implicit:

- **Categorization covers 3 of EmailOrbit's 9 target categories**
  (Work/Personal/Other) because the Enron training data has no real
  Finance/Shopping/Travel/Social/Promotions examples (Phase 6). Adding
  the other 6 would need a differently-sourced or hand-labeled dataset.
- **Priority detection is trained on heuristic pseudo-labels**, not
  real-world ground truth (Phase 6/7) — its reported F1 measures
  agreement with the heuristic rule, not actual urgency judgment.
  Collecting real user feedback (Phase 10's `UserFeedback` table
  already exists for exactly this) over time would let a future
  iteration retrain against real labels instead.
- **Duplicate detection is exact-match only** (Phase 10) — a hash of
  normalized content. Near-duplicates that differ by a signature line,
  a re-quoted thread, or minor rewording aren't caught. Fuzzy/semantic
  matching (e.g. embedding similarity) would catch more at the cost of
  real complexity and cost.
- **Smart replies' LLM path sends email content to a third-party API**
  when configured (Phase 9) — an explicit, documented tradeoff, not an
  oversight; the template fallback exists specifically so this is
  optional.
- **No automated retraining loop** — `UserFeedback` corrections
  (Phase 10) are applied immediately to the corrected email but aren't
  fed back into Phase 6's training scripts automatically. A future
  version could periodically retrain on accumulated corrections.
- **Deployment (Phase 12) is out of scope** per project decision — this
  project runs locally (`flask run`) against a local/managed MySQL
  instance and was never containerized, load-tested, or deployed to a
  hosting platform.
