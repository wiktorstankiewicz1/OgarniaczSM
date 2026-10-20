# Setting Up Visual C++ Redistributable Bundling

To include Visual C++ Redistributables in the installer, you need to download and place the installer file in the project directory.

## Step 1: Download VC++ Redistributable

Download the Visual C++ 2015-2022 Redistributable (x64) from Microsoft:

**Direct Download:**
- https://aka.ms/vs/17/release/vc_redist.x64.exe

**Or search for:**
- "Microsoft Visual C++ 2015-2022 Redistributable (x64)"

## Step 2: Place in Project Root

Save the downloaded file as `vc_redist.x64.exe` in the project root directory:

```
OgarniaczSM/
├── vc_redist.x64.exe    ← Place it here
├── build_installer.py
├── GENERATE_INSTALLER_EXE.py
├── main.py
└── ...
```

## Step 3: Rebuild Installer

After placing `vc_redist.x64.exe` in the project root, rebuild the installer:

```bash
python GENERATE_INSTALLER_EXE.py
```

The installer will now:
1. ✅ Check if VC++ Redistributables are already installed
2. ✅ If not installed, automatically install them silently
3. ✅ Continue with app installation

## How It Works

- The installer checks the Windows registry and tries to load `VCRUNTIME140.dll` to detect if VC++ Redistributables are installed
- If not found, it extracts the bundled `vc_redist.x64.exe` and runs it silently (`/install /quiet /norestart`)
- Installation happens before copying the app files, ensuring the app will work immediately

## File Size

The VC++ Redistributable installer is ~25 MB, which will increase the installer EXE size. This is acceptable because:
- It's a one-time download per PC
- It ensures the app works on all Windows PCs without manual steps
- Most modern PCs already have it installed (so it won't reinstall)

## Optional: Skip Bundling

If you prefer not to bundle it (smaller installer size), you can:
1. Don't place `vc_redist.x64.exe` in the project root
2. The installer will detect it's missing and prompt the user to install manually
3. Provide a link to download it

However, bundling is recommended for the best user experience.













