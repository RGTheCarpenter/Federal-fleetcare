# FleetCare Full Stack

FleetCare is now a local full-stack fleet management app inspired by Drivvo.

## Features

- User registration and login
- SQLite database persistence
- Vehicle records with status and odometer
- Driver records and vehicle assignments
- Maintenance logs with next service targets
- Fuel logs with spend and price-per-gallon tracking
- Reminder-based alerts for due and overdue work
- Downloadable PDF fleet report
- Mobile-friendly dashboard for phones and tablets

## Run it

1. Open a terminal in this folder.
2. Run:

```powershell
python server.py
```

3. Open `http://127.0.0.1:8000`
4. Create your company account and start adding data.

## Host it for your team

This app can now run on a hosted server because it reads `HOST` and `PORT` from environment variables instead of being locked to your computer only.

Production environment variables:

- `HOST=0.0.0.0`
- `PORT`
- `SECRET_KEY`
- `COMPANY_INVITE_CODE`
- `DATABASE_URL`
- `PGSSLMODE=require`

Basic deployment shape:

1. Put this project on a server or hosting platform that can run `python server.py`.
2. Set `HOST=0.0.0.0`
3. Set a strong `SECRET_KEY`.
4. Set a private `COMPANY_INVITE_CODE` that only approved team members know.
5. Point `DATABASE_URL` at a managed PostgreSQL database.
6. Let the platform provide `PORT`, or set one yourself.
7. Keep the app running with:

```text
python server.py
```

Included deployment helpers:

- `Procfile` for simple process-based hosting
- `Dockerfile` for container deployment
- `.env.example` for required cloud settings
- `/health` endpoint for uptime or platform health checks
- secure cookie support when the host sends `X-Forwarded-Proto: https`

Important note:

- For real cloud use, set `DATABASE_URL` so the app uses PostgreSQL.
- SQLite remains available as a local fallback when `DATABASE_URL` is not set.

## Suggested cloud setup

For a small team, a good production shape is:

1. One web service running this app
2. One managed PostgreSQL database
3. Environment variables from `.env.example`
4. HTTPS enabled by the hosting platform

Good hosting options for this architecture include Render, Railway, Fly.io, and similar platforms that support Python apps plus managed PostgreSQL.

## Render deployment

This project now includes:

- `render.yaml` for a Render Blueprint
- `DEPLOY_RENDER.md` with step-by-step setup

Render will create:

- one web service for the app
- one managed PostgreSQL database
- a generated `SECRET_KEY`
- a private `COMPANY_INVITE_CODE` prompt
- a connected `DATABASE_URL`

If you deploy with the Blueprint, your team will use the public HTTPS URL Render gives you.

## Phone app install

FleetCare can be installed on iPhone and Android as a browser-based phone app.

See `INSTALL_PHONE_APP.md` for step-by-step instructions.

## Native app wrapper

This project is also scaffolded for a real native wrapper using Capacitor.

Files added for that path:

- `package.json`
- `capacitor.config.json`
- `static-capacitor-shell/index.html`
- `MOBILE_APP_SETUP.md`

That setup is intended for generating Android and iOS store builds on a machine with Node.js, Android Studio, and Xcode.

## Files

- `server.py`: app entry point
- `fleetcare_app/app.py`: routing, pages, and business logic
- `fleetcare_app/db.py`: SQLite schema and connections
- `fleetcare_app/auth.py`: password hashing and cookie signing
- `fleetcare_app/pdf.py`: built-in PDF generator
- `static/styles.css`: app styling

## Notes

- The SQLite database file is created automatically as `fleetcare.db`.
- Passwords are hashed locally before being stored.
- New account registration requires `COMPANY_INVITE_CODE`.
- Alerts in this version are in-app dashboard alerts.
- PDF reports are generated locally and download from the browser.
- `.fleetcare-secret` is created automatically to sign login cookies. Keep it private and persistent on the server.
- In production, prefer `SECRET_KEY` from environment variables instead of the local secret file.

## Good next upgrades

- Email or WhatsApp alerts
- File attachments for invoices and inspections
- CSV import/export
- Role-based access for managers and drivers
- Background jobs for scheduled alerts and report delivery
