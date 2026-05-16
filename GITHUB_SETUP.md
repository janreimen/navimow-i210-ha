# Upload to GitHub

## Quick Start

### 1. Create a new GitHub repository

1. Go to https://github.com/new
2. **Repository name:** `navimow-i210-ha`
3. **Description:** `Segway Navimow i210 Home Assistant integration (domain: navimow_i210)`
4. **Visibility:** Public
5. **Initialize with:** None (we already have files)
6. Click **Create repository**

### 2. Clone and push locally

```bash
# Create and enter a new directory
mkdir navimow-i210-ha && cd navimow-i210-ha

# Initialize git
git init

# Add the remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/navimow-i210-ha.git

# Configure git
git config user.email "your@email.com"
git config user.name "Your Name"

# Copy all files from this repo into the directory
cp -r /home/claude/navimow_i210_release/* .

# Stage all files
git add .

# Initial commit
git commit -m "Initial release: Navimow i210 MQTT-first integration v2.0.0"

# Push to GitHub
git branch -M main
git push -u origin main
```

### 3. Verify on GitHub

- Visit `https://github.com/YOUR_USERNAME/navimow-i210-ha`
- Should show:
  - `custom_components/navimow_i210/` (16 .py files + manifest.json)
  - `README.md`, `LICENSE`, `CHANGELOG.md`
  - `.github/workflows/validate.yml`
  - `.gitignore`, `hacs.json`

## File Structure

```
navimow-i210-ha/
├── .github/
│   └── workflows/
│       └── validate.yml           ← CI validation
├── custom_components/
│   └── navimow_i210/
│       ├── __init__.py            ← Main integration setup
│       ├── auth.py                ← OAuth2 implementation
│       ├── config_flow.py         ← Config UI
│       ├── coordinator.py         ← Data fetching & MQTT hooks
│       ├── const.py               ← Constants & error codes
│       ├── entity.py              ← Base entity class
│       ├── services.py            ← HA services
│       ├── sensor.py              ← 45+ sensors
│       ├── binary_sensor.py       ← Binary sensors (8)
│       ├── switch.py              ← Settings switches (6)
│       ├── select.py              ← Selectors (work mode)
│       ├── number.py              ← Numbers (cutting height)
│       ├── button.py              ← Buttons (start/pause/dock)
│       ├── device_tracker.py      ← GPS tracker
│       ├── lawn_mower.py          ← Lawn mower entity
│       ├── update.py              ← Firmware updates
│       └── manifest.json          ← Integration metadata
├── .gitignore
├── CHANGELOG.md
├── LICENSE                        ← Apache 2.0
├── README.md
├── GITHUB_SETUP.md               ← This file
└── hacs.json                      ← HACS metadata
```

## After First Push

### Add to HACS

1. In Home Assistant HACS, click **⋮ → Custom repositories**
2. Add: `https://github.com/YOUR_USERNAME/navimow-i210-ha`
3. Category: **Integration**
4. Click **Install**

### Add Release Tags (optional but recommended)

```bash
# Tag the initial release
git tag -a v2.0.0 -m "Initial release: MQTT-first, full sensor coverage"
git push origin v2.0.0

# Future releases
git tag -a v2.0.1 -m "Bug fix: MQTT reconnect"
git push origin v2.0.1
```

### Enable GitHub Pages (optional)

1. Go to **Settings → Pages**
2. **Source:** Deploy from a branch
3. **Branch:** main, /root
4. Your docs appear at `https://YOUR_USERNAME.github.io/navimow-i210-ha/`

## Updating the Integration

```bash
# Make changes locally, then:
git add .
git commit -m "Feature: Add XYZ"
git push origin main

# Tag a new release
git tag -a v2.0.2 -m "Feature: Add XYZ"
git push origin v2.0.2
```

## Troubleshooting

**Files won't push?**
- Check `.gitignore` isn't blocking anything: `git status`
- Try: `git push --set-upstream origin main`

**GitHub says repo exists?**
- Repository URL must be HTTPS: `https://github.com/YOUR_USERNAME/navimow-i210-ha.git`
- Make sure you're pushing to the right remote: `git remote -v`

**Permission denied?**
- Ensure your SSH key is added: `ssh -T git@github.com`
- Or switch to HTTPS: `git remote set-url origin https://github.com/YOUR_USERNAME/navimow-i210-ha.git`

---

## Next Steps

1. **Test in HA:** Install via HACS, add integration
2. **Iterate:** Push fixes as tags (v2.0.1, v2.0.2, etc.)
3. **Promote:** Link in Home Assistant forums / Reddit / Discord
4. **Maintain:** Respond to issues, accept PRs

Happy hacking! 🚀
