# Setting Up Ollama with Cursor (Bypassing SSRF Block)

## The Problem
Cursor blocks `localhost` and `127.0.0.1` connections for security (SSRF protection). The error you're seeing:
```
"connection to private IP is blocked"
"ssrf_blocked"
```

## Solution Options

### Option 1: Use ngrok (Easiest, but exposes to internet)

1. **Install ngrok**: Download from https://ngrok.com/download

2. **Create tunnel**:
   ```powershell
   ngrok http 11434
   ```

3. **Copy the HTTPS URL** (looks like `https://abc123.ngrok-free.app`)

4. **In Cursor Settings**:
   - Override OpenAI Base URL: `https://abc123.ngrok-free.app/v1`
   - OpenAI API Key: `ollama`
   - Model name: `qwen2.5-coder:14b`

**Note**: This exposes Ollama to the internet. Use ngrok's authentication to protect it.

---

### Option 2: Use Local Domain (Might work if Cursor doesn't resolve it)

1. **Edit hosts file as Administrator**:
   ```powershell
   # Run PowerShell as Admin
   Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "127.0.0.1 ollama.local"
   ```

2. **In Cursor Settings**:
   - Override OpenAI Base URL: `http://ollama.local:11434/v1`
   - OpenAI API Key: `ollama`

**Note**: This might not work if Cursor resolves domains on their backend.

---

### Option 3: Use Cloudflare Tunnel (More secure than ngrok)

1. Install Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/

2. Create tunnel:
   ```powershell
   cloudflared tunnel --url http://localhost:11434
   ```

3. Use the provided URL in Cursor settings.

---

### Option 4: Check Cursor Advanced Settings

Some users report that Cursor has hidden settings. Try:
- Press `Ctrl + Shift + P`
- Type: "Preferences: Open Settings (JSON)"
- Look for settings like:
  ```json
  {
    "cursor.aiSettings.allowLocalhost": true,
    "cursor.aiSettings.allowPrivateIPs": true
  }
  ```

---

## Recommended: ngrok with Auth

1. **Sign up for free ngrok account**: https://dashboard.ngrok.com/signup

2. **Get your authtoken** from dashboard

3. **Configure ngrok**:
   ```powershell
   ngrok config add-authtoken YOUR_TOKEN
   ```

4. **Start tunnel**:
   ```powershell
   ngrok http 11434 --domain=your-custom-domain.ngrok-free.app
   ```

5. **Use in Cursor**: `https://your-custom-domain.ngrok-free.app/v1`

This gives you a stable URL and basic protection.

---

## Alternative: Use Different Tool

If Cursor's SSRF protection is too strict, consider:
- **Continue Code** (VS Code extension with Ollama support)
- **Roo Code** (you mentioned trying this)
- **Continue.dev** (open-source, supports Ollama natively)

These tools are designed to work with local models without SSRF issues.

