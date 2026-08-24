# KC Coaching Classes — Attendance & Fee Manager

A free, no-payment-gateway attendance and fee tracker for a single-teacher coaching class.
Runs as a Flask web app and installs on Android as a **PWA** (Add to Home Screen) — no
Android Studio, no Play Store needed.

## Features

- Student roster (name, batch, parent name, WhatsApp number, fee amount)
- Daily attendance marking, per-batch, with monthly % report
- Fee ledger per month: generate dues, record payments, auto status (pending/partial/paid)
- PDF fee receipts (auto-generated, downloadable)
- WhatsApp reminders and receipts via free `wa.me` deep links (opens WhatsApp with
  message pre-filled — you just tap Send). No WhatsApp Business API, no cost.
- Installable on Android home screen (PWA) — works full-screen like a native app
- Single teacher login

## 1. Run locally

```bash
cd kc_coaching
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** in your browser.

**First login:** username `admin`, password `changeme123`.
Change this immediately — see "Changing the admin password" below.

**Set up password recovery (do this once):** add an environment variable
`ADMIN_RECOVERY_KEY` (any secret phrase you'll remember) — locally in a `.env` file,
or on Render under Environment. If you ever forget your password, go to
`/forgot-password` on the login page, enter this key plus a new password.
Without this set, there's no way to recover a lost password except editing the
database directly.

**Auto-logout:** the app logs out automatically after 5 minutes of inactivity —
this is a security measure since it's reachable from the public internet.

**Batches:** before adding students, create at least one Batch (Students → Manage
Batches → Add Batch). Students are assigned to a batch, which drives attendance
marking, fee reports, and filtering throughout the app.

**Phone numbers:** just enter the 10-digit mobile number — no country code needed.
The app assumes India (+91) by default when building WhatsApp links.

## 2. Changing the admin password

Run this once, from the project folder (with venv active):

```bash
python3 -c "
from app import app, db
from models import Admin
with app.app_context():
    a = Admin.query.filter_by(username='admin').first()
    a.set_password('YOUR-NEW-PASSWORD')
    db.session.commit()
    print('Password updated')
"
```

Or create a brand-new admin with a different username using:
```bash
flask create-admin
```

## 3. Deploy free on Render (step by step)

This project is already Render-ready: `Procfile`, `runtime.txt`, `render.yaml`, and
`psycopg2-binary` (Postgres driver) are all included. Render's free web service tier has
two things worth knowing upfront: it **spins down after 15 minutes of no traffic** (next
visit takes ~30-60 sec to wake up — fine for a tuition app used a few times a day), and
its own free Postgres **expires after 30 days**. So we pair Render with a free database
from **Neon** instead, which doesn't expire.

**Step 1 — Push to GitHub**
Create a new (private is fine) GitHub repo and push this whole `kc_coaching` folder to it.

**Step 2 — Create a free database on Neon**
1. Go to [neon.tech](https://neon.tech) → sign up free → New Project.
2. Copy the connection string shown (looks like `postgresql://user:pass@ep-xxx.neon.tech/dbname`).
   Keep this handy for Step 4.

**Step 3 — Create the Web Service on Render**
1. Go to [render.com](https://render.com) → New → Web Service → connect your GitHub repo.
2. Render should auto-detect `render.yaml` and pre-fill the build/start commands. If not,
   set manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
3. Plan: **Free**.

**Step 4 — Set environment variables**
In the service's Environment tab:
- `SECRET_KEY` — Render auto-generates this if using `render.yaml`, otherwise set any random string.
- `DATABASE_URL` — paste the Neon connection string from Step 2.

**Step 5 — Deploy**
Click Create Web Service / Deploy. You'll get a live URL like `https://kc-coaching-classes.onrender.com`.

**Step 6 — Change the default password immediately**
Run this from your own machine (with `venv` active), pointing at the *same* Neon database
so it updates the live app:
```bash
DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/dbname" python3 -c "
from app import app, db
from models import Admin
with app.app_context():
    a = Admin.query.filter_by(username='admin').first()
    a.set_password('YOUR-NEW-PASSWORD')
    db.session.commit()
    print('Password updated')
"
```

**Step 7 — Install on your Android phone**
Open the onrender.com URL in Chrome → menu → **Add to Home Screen**.

## 4. Install on Android as an app (PWA — no Android Studio)

1. Open your deployed URL (or local IP if on the same WiFi) in **Chrome** on your phone.
2. Tap the ⋮ menu → **Add to Home Screen** (or **Install App** if prompted automatically).
3. It now opens full-screen with its own icon, exactly like a native app.

## 5. WhatsApp number format

Enter numbers as `91XXXXXXXXXX` (country code + 10 digits, no `+`, no spaces, no dashes).
This is required for the `wa.me` links to work correctly.

## 6. Everyday usage flow

1. **Add students** once (Students → Add Student).
2. **Each class day:** Attendance → pick batch/date → mark Present/Absent → Save.
   Tap "Notify" next to a student to WhatsApp their parent an absence alert.
3. **Start of month:** Fees → "Generate Fee Entries" for the new month (auto-fills each
   student's fee amount).
4. **As payments come in:** Fees → enter amount paid → Update Paid. Status auto-updates.
5. **Reminders:** Fees → "Remind on WhatsApp" next to any pending/partial entry.
6. **Reports:** monthly attendance % and fee collection totals under Reports.

## Project structure

```
kc_coaching/
├── app.py              # Routes
├── models.py            # Database models
├── utils.py             # WhatsApp links + PDF receipt generation
├── requirements.txt
├── templates/            # HTML pages
├── static/
│   ├── css/style.css
│   ├── manifest.json     # PWA manifest
│   ├── service-worker.js # Offline caching
│   └── icons/
└── instance/             # SQLite database (created automatically, git-ignore this)
```

## What I'd build next (optional, tell me if you want any of these)

- Bulk WhatsApp reminders (one tap for all pending fees in a batch, opens each link in sequence)
- CSV/Excel export of attendance and fee reports (you've used pandas/openpyxl before — easy add)
- Overdue fee auto-highlighting based on due date
- Multi-batch fee amounts / discounts per student
- Parent-side read-only view (share a link so parents can check their own dues)
