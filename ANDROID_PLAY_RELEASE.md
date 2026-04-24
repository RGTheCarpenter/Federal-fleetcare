# Android Release And Play Console

## What is already prepared

- Android app name: `FleetCare Mobile`
- Android icon branding: updated adaptive launcher icon
- Native offline fallback screen
- Native share support
- Local reminder notifications support
- Gradle release signing config reads `android/keystore.properties`

## 1. Create a release keystore

Use Android Studio's terminal or Windows PowerShell in the project root.

If `keytool` is already available:

```powershell
keytool -genkeypair -v `
  -keystore android\release-keystore.jks `
  -alias fleetcare-release `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000
```

If `keytool` is not in your PATH, use the Android Studio bundled JBR path:

```powershell
& "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe" -genkeypair -v `
  -keystore android\release-keystore.jks `
  -alias fleetcare-release `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000
```

## 2. Create `android\keystore.properties`

Copy `android\keystore.properties.example` to `android\keystore.properties` and replace the values:

```properties
storeFile=release-keystore.jks
storePassword=your-store-password
keyAlias=fleetcare-release
keyPassword=your-key-password
```

Keep `android\keystore.properties` private and do not commit it.

## 3. Build the signed Android App Bundle

From Android Studio:

1. Open the `android` project
2. Wait for Gradle sync
3. Click `Build`
4. Click `Generate Signed App Bundle / APK`
5. Choose `Android App Bundle`
6. Select `android\release-keystore.jks`
7. Use alias `fleetcare-release`
8. Choose the `release` build type
9. Finish the wizard

The `.aab` file will be created under:

`android\app\release`

## 4. Upload to Google Play internal testing

1. Open [Google Play Console](https://play.google.com/console)
2. Create your app if this is the first upload
3. Complete the required store listing, privacy policy, app content, and data safety forms
4. Go to `Testing` > `Internal testing`
5. Create a release
6. Upload the generated `.aab`
7. Add internal testers by email
8. Roll out the internal test release

## Important notes

- Full remote push notifications still need Firebase / FCM and a real `google-services.json`
- The app already includes local on-device reminder notifications
- Test the offline screen, sharing, and photo uploads on a real Android phone before submitting to Play
