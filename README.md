# Passport Photo Maker (offline Windows desktop app)

Customer photos never leave the PC. The AI model is bundled inside the app - no internet, Python or tools needed on the shop PC.

## Get the app (one-time, on any device with a browser)
1. Open your GitHub repo. Delete the old files, then upload ALL files from this zip (keep the `.github` folder).
2. Go to **Actions -> Build Windows app -> Run workflow** (about 10-15 min).
   The build fails automatically if the app's built-in self-test fails.
3. Open the finished run and download **PassportPhotoMaker-Windows**.
4. Run `PassportPhotoMaker-Setup.exe` on the shop PC (no admin rights needed) - or unzip `PassportPhotoMaker-portable.zip` and run `PassportPhotoMaker.exe`.

## Using it
Add photos (button / folder / drag-drop) -> set copies per photo -> *Generate sheet* -> Save (PNG/JPG/PDF) or Print.

## Extra photo sizes
Create `%LOCALAPPDATA%\PassportPhotoMaker\presets.json`:
`[{"name":"My ID","country":"India","w_mm":30,"h_mm":40,"head_ratio":0.7,"notes":"..."}]`

## Troubleshooting
Log file: `%LOCALAPPDATA%\PassportPhotoMaker\log.txt`
