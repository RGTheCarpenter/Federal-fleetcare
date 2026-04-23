# Deploy FleetCare on Render

## What you need

- A GitHub, GitLab, or Bitbucket repository with this project
- A Render account

## Fastest setup

1. Upload this project to a Git repository.
2. In Render, click **New** > **Blueprint**.
3. Connect the repository that contains this project.
4. Render will detect `render.yaml`.
5. Review the resources:
   - `fleetcare-web` web service
   - `fleetcare-db` PostgreSQL database
6. Click **Deploy Blueprint**.
7. When Render asks for `COMPANY_INVITE_CODE`, enter a private code for your company.
   Example: `FederalFleet-2026-Invite`
8. Wait for Render to finish provisioning and deploying.
9. Open the generated `onrender.com` URL for `fleetcare-web`.
10. Create your first company account in the app.

## Existing Render services

If your Blueprint was already deployed before `COMPANY_INVITE_CODE` was added:

1. Open `fleetcare-web` in Render.
2. Go to **Environment**.
3. Add `COMPANY_INVITE_CODE`.
4. Set it to a private code your team will use.
5. Save changes and redeploy.

## What Render creates from this project

- A public web service
- A managed PostgreSQL database
- A generated app secret
- A private company invite code that you provide during setup
- Automatic `DATABASE_URL` wiring from the database to the app
- Health checks using `/health`

## How your team uses it

After deployment, your team uses the public HTTPS URL from Render, for example:

`https://fleetcare-web.onrender.com`

Share that URL with your team. They open it in a browser on phone or desktop, sign in, and use the app.

Only share the company invite code with people who should be allowed to create accounts.

## If you want your own domain

After the app is live:

1. Open the web service in Render
2. Go to **Settings** > **Custom Domains**
3. Add your domain, such as `fleet.yourcompany.com`
4. Follow Render's DNS instructions

## If you update the code later

Push changes to the same Git branch connected to Render. Render will redeploy automatically.
