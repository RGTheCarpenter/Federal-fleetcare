# FleetCare Native App Setup

FleetCare is now scaffolded to be wrapped as a real native app using Capacitor.

This wrapper points to the hosted app:

- `https://fleetcare-web.onrender.com`

## What this gives you

- Android app project for Google Play
- iPhone app project for the Apple App Store
- Native app icon, splash, and status bar configuration path
- A real installable app package instead of only browser home-screen install

## Important limitation

This workspace does not currently have Node.js, npm, Android Studio, or Xcode available, so the native platform folders could not be generated here automatically.

The Capacitor config and package setup are ready. On a development machine with the required tools, run the steps below.

## 1. Install prerequisites

- Node.js
- npm
- Android Studio for Android builds
- Xcode on a Mac for iPhone builds

## 2. In this project folder, install dependencies

```powershell
npm install
```

## 3. Generate the native projects

```powershell
npx cap add android
npx cap add ios
npx cap sync
```

## 4. Open the native projects

Android:

```powershell
npx cap open android
```

iPhone:

```powershell
npx cap open ios
```

## 5. App store submission flow

Android:

1. Open the Android project in Android Studio
2. Set the final app icon, splash screen, package details, and signing key
3. Build an `.aab`
4. Upload to Google Play Console

iPhone:

1. Open the iOS project in Xcode on a Mac
2. Set your Apple Developer Team
3. Set app icons, launch screen, bundle details, and signing
4. Archive the app
5. Upload through App Store Connect

## Current wrapper config

- App name: `FleetCare`
- App ID: `com.rgthecarpenter.federalfleetcare`
- Hosted app URL: `https://fleetcare-web.onrender.com`

## Notes

- Because the native wrapper loads the live hosted app, users still need internet access unless you later add stronger offline features.
- If you want deeper native behavior later, Capacitor plugins can add push notifications, camera, files, biometrics, and more.
