# Docker Setup for TraitKeeper (Windows)

## 🚨 Your Error Explained

```
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

**This means:** Docker Desktop is not running on your Windows machine.

---

## ✅ Step-by-Step Fix

### Step 1: Install Docker Desktop (If Not Installed)

1. **Download Docker Desktop for Windows:**
   - Visit: <https://www.docker.com/products/docker-desktop/>
   - Click "Download for Windows"

2. **Install Docker Desktop:**
   - Run the installer
   - Follow the installation wizard
   - **Important:** Enable WSL 2 when prompted (recommended)

3. **Restart your computer** (required after first install)

---

### Step 2: Start Docker Desktop

1. **Open Docker Desktop:**
   - Press `Windows Key`
   - Type "Docker Desktop"
   - Click to open

2. **Wait for Docker to fully start:**
   - You'll see "Docker Desktop is running" in the system tray
   - The whale icon should be visible (not animated)
   - First time startup takes 1-2 minutes

3. **Verify Docker is running:**

   ```powershell
   docker --version
   docker ps
   ```

   **Expected output:**

   ```
   Docker version 24.0.x, build xxx
   CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
   ```

---

### Step 3: Configure Docker Desktop (Optional but Recommended)

1. **Open Docker Desktop Settings:**
   - Right-click Docker icon in system tray
   - Click "Settings"

2. **Resources → Advanced:**
   - **CPUs:** Allocate at least 2 CPUs (4 recommended)
   - **Memory:** Allocate at least 4GB RAM (8GB recommended)
   - Click "Apply & Restart"

3. **General:**
   - ✓ "Start Docker Desktop when you sign in"
   - ✓ "Use the WSL 2 based engine" (recommended)

---

### Step 4: Run TraitKeeper with Docker

Now that Docker is running, you can start TraitKeeper:

```powershell
# Navigate to project directory
cd "C:\Users\LENOVO PC\PROJECTS\website\traitskeeper\traitkeeper"

# Make sure .env file exists
cp .env.example .env

# Edit .env with your settings (if needed)
notepad .env

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

---

## 📊 Verifying Everything Works

### Check Running Containers

```powershell
docker ps
```

**Expected output:**

```
CONTAINER ID   IMAGE                    STATUS         PORTS                    NAMES
xxx            traitkeeper-main         Up 2 minutes   0.0.0.0:8000->8000/tcp   traitkeeper-main
xxx            traitkeeper-data         Up 2 minutes                            traitkeeper-data
xxx            postgres:15-alpine       Up 2 minutes   0.0.0.0:5432->5432/tcp   traitkeeper-postgres
xxx            redis:7-alpine           Up 2 minutes   0.0.0.0:6379->6379/tcp   traitkeeper-redis
```

### Check Logs

```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f main
docker-compose logs -f data
```

### Access Application

- **Main App:** <http://localhost:8000>
- **Admin Panel:** <http://localhost:8000/admin/>

---

## 🛠️ Common Issues & Fixes

### Issue 1: "Docker Desktop is not running"

**Symptoms:**

```
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

**Fix:**

1. Open Docker Desktop from Start Menu
2. Wait for it to fully start (watch system tray icon)
3. Try `docker ps` to verify
4. Run `docker-compose up -d` again

---

### Issue 2: "WSL 2 installation is incomplete"

**Symptoms:**

```
Docker Desktop requires Windows Subsystem for Linux 2 (WSL 2)
```

**Fix:**

```powershell
# Open PowerShell as Administrator
wsl --install
wsl --set-default-version 2

# Restart computer
# Start Docker Desktop again
```

---

### Issue 3: "Port 8000 already in use"

**Symptoms:**

```
Error starting userland proxy: listen tcp4 0.0.0.0:8000: bind: address already in use
```

**Fix Option 1 - Stop existing process:**

```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace XXXX with PID from above)
taskkill /PID XXXX /F
```

**Fix Option 2 - Change TraitKeeper port:**

```yaml
# Edit docker-compose.yml
# Change:
ports:
  - "8000:8000"
# To:
ports:
  - "8001:8000"

# Then access at http://localhost:8001
```

---

### Issue 4: "Cannot connect to Docker daemon"

**Symptoms:**

```
error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/...":
```

**Fix:**

1. **Check if Docker Desktop is actually running:**
   - Look for whale icon in system tray
   - Should say "Docker Desktop is running"

2. **Restart Docker Desktop:**
   - Right-click Docker icon
   - Click "Restart Docker Desktop"
   - Wait 30 seconds

3. **Still not working? Reinstall Docker:**

   ```powershell
   # Uninstall Docker Desktop
   # Download latest version from docker.com
   # Install and restart computer
   ```

---

### Issue 5: "docker-compose: command not found"

**Symptoms:**

```
'docker-compose' is not recognized as an internal or external command
```

**Fix:**

Docker Compose v2 is built into Docker Desktop. Use `docker compose` (no hyphen):

```powershell
# Old way (Docker Compose v1)
docker-compose up -d

# New way (Docker Compose v2 - built into Docker Desktop)
docker compose up -d
```

**Or create an alias:**

```powershell
# Add to PowerShell profile
Set-Alias docker-compose "docker compose"
```

---

### Issue 6: Slow build/startup

**Symptoms:**

- Docker taking 5+ minutes to start
- Build taking very long

**Fix:**

1. **Enable WSL 2 backend:**
   - Docker Desktop → Settings → General
   - ✓ "Use the WSL 2 based engine"

2. **Increase resources:**
   - Docker Desktop → Settings → Resources
   - Increase CPUs to 4
   - Increase Memory to 8GB

3. **Clean up Docker:**

   ```powershell
   # Remove unused images and containers
   docker system prune -a

   # Remove unused volumes
   docker volume prune
   ```

---

## 🎯 Complete Fresh Start

If everything is broken, start fresh:

```powershell
# 1. Stop all containers
docker-compose down

# 2. Remove all containers and volumes
docker-compose down -v

# 3. Remove images
docker system prune -a

# 4. Restart Docker Desktop
# Right-click Docker icon → Restart Docker Desktop

# 5. Start fresh
docker-compose up -d --build
```

---

## 📋 Docker Desktop Checklist

Before running `docker-compose up`:

- [ ] Docker Desktop is installed
- [ ] Docker Desktop is running (whale icon in system tray)
- [ ] `docker ps` command works
- [ ] WSL 2 is enabled (Settings → General)
- [ ] At least 4GB RAM allocated (Settings → Resources)
- [ ] `.env` file exists and configured
- [ ] No other services using port 8000

---

## 🚀 Quick Start Commands

```powershell
# Start Docker Desktop (from Start Menu)
# Wait for it to fully start...

# Navigate to project
cd "C:\Users\LENOVO PC\PROJECTS\website\traitskeeper\traitkeeper"

# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down

# Restart a specific service
docker compose restart main

# Rebuild and start
docker compose up -d --build
```

---

## 🎓 Understanding Docker Compose Commands

| Command | What it does |
|---------|--------------|
| `docker compose up` | Start services (attached, see logs) |
| `docker compose up -d` | Start services (detached, in background) |
| `docker compose down` | Stop and remove containers |
| `docker compose down -v` | Stop, remove containers AND volumes (data!) |
| `docker compose logs -f` | View logs (follow mode) |
| `docker compose ps` | List running containers |
| `docker compose restart main` | Restart main service |
| `docker compose exec main bash` | Open shell in main container |
| `docker compose up --build` | Rebuild images and start |

---

## 💡 Pro Tips

### 1. Auto-start Docker Desktop

Settings → General → ✓ "Start Docker Desktop when you sign in"

### 2. Use Docker Compose v2 (built-in)

```powershell
# Modern way (recommended)
docker compose up -d

# Old way (requires separate install)
docker-compose up -d
```

### 3. View specific service logs

```powershell
# Just main app
docker compose logs -f main

# Just data service
docker compose logs -f data

# Last 50 lines
docker compose logs --tail=50 main
```

### 4. Run Django commands in container

```powershell
# Migrations
docker compose exec main python manage.py migrate

# Create superuser
docker compose exec main python manage.py createsuperuser

# Django shell
docker compose exec main python manage.py shell

# Collect static files
docker compose exec main python manage.py collectstatic
```

### 5. Access database directly

```powershell
# Connect to PostgreSQL
docker compose exec postgres psql -U traitkeeper_user -d traitkeeper_db

# List tables
\dt

# Query data
SELECT * FROM nft_data_nftcollection;

# Exit
\q
```

---

## 🆘 Still Having Issues?

1. **Check Docker Desktop Dashboard:**
   - Open Docker Desktop
   - Click "Containers" tab
   - See which containers are running/failing

2. **Check Windows Firewall:**
   - May block Docker ports
   - Add exception for Docker Desktop

3. **Update Docker Desktop:**
   - Help → Check for Updates
   - Install latest version

4. **Check system requirements:**
   - Windows 10/11 (64-bit, Pro/Enterprise/Education)
   - Virtualization enabled in BIOS
   - WSL 2 feature enabled

---

## 📞 Getting Help

- **Docker Desktop Troubleshooting:** <https://docs.docker.com/desktop/troubleshoot/overview/>
- **WSL 2 Installation:** <https://learn.microsoft.com/en-us/windows/wsl/install>
- **TraitKeeper Issues:** See [QUICK_START.md](./QUICK_START.md)

---

**Once Docker Desktop is running, you're ready to go!** 🚀
