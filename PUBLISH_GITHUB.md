# Publish FleetCare to GitHub

## Current status

The repository is already initialized on `main`, and the project files are staged locally.

## One-time Git identity setup

Run these with your real name and GitHub email:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## Create the first commit

```powershell
git commit -m "Initial FleetCare app with Render deployment"
```

## Create the GitHub repository

1. Go to GitHub
2. Click **New repository**
3. Choose a repo name such as `fleetcare`
4. Leave it empty:
   - do not add a README
   - do not add a `.gitignore`
   - do not add a license
5. Click **Create repository**

## Connect this folder to GitHub

Replace `YOUR-USERNAME` and `YOUR-REPO` below:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```

## Deploy on Render

After the repo is on GitHub:

1. Sign in to Render
2. Click **New** > **Blueprint**
3. Connect the GitHub repo
4. Render will read `render.yaml`
5. Click **Deploy Blueprint**

Your team will then use the public Render URL.
