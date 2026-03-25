# JARVIS CLI

JARVIS (Tools for Life Hack) - A powerful CLI built with Python and Typer for system automation, database management, and application maintenance.

**Version:** v0.16.0

## 🚀 Installation

### 1. Download latest release (Recommended)

You can download the latest pre-built executable for Linux (Ubuntu 22.04+/Debian) directly from GitHub:

```bash
mkdir -p ~/.local/bin
# Download and extract the binary to ~/.local/bin
curl -L https://github.com/pigdome/jarvis/releases/latest/download/jarvis.tar.gz | tar -xz -C ~/.local/bin
chmod +x ~/.local/bin/jarvis
```

Make sure `~/.local/bin` is in your `$PATH`.

### 2. Build from source

Requires Python 3.12+.

```bash
git clone https://github.com/pigdome/jarvis.git
cd jarvis
bash build.sh
```

---

## 📖 Usage

```bash
jarvis [CATEGORY] [COMMAND] [OPTIONS]
```

To see the full command structure:
```bash
jarvis help
```

---

## 🛠️ Categories & Commands

### 🚀 app — Applications & Services
Specific maintenance commands for library and repository systems.

| Command | Description |
|---|---|
| `jarvis app koha stats [DB]` | Show Koha database statistics (Biblios, Items, Issues) |
| `jarvis app dspace init-db` | Create DSpace user and database in PostgreSQL |
| `jarvis app dspace stats [DB]` | Show DSpace database statistics (Items, Collections) |

### 🗄️ db — Database Utilities
Direct database access and maintenance. Now supports passwordless access via `sudo`.

| Command | Description |
|---|---|
| `jarvis db mysql` | Open MySQL client using `debian.cnf` (root) |
| `jarvis db psql` | Open PostgreSQL client as `postgres` user |
| `jarvis db pg-restore DB FILE` | Drop, Create, and Restore Postgres from `.sql.gz` dump |
| `jarvis db pg-dump DB` | Dump a PostgreSQL database |
| `jarvis db mysqldump DB` | Dump a MySQL database |

### 🏗️ sys — Infrastructure & System
System-level management and setup.

| Command | Description |
|---|---|
| `jarvis sys init` | **Root only.** Full server setup (Apt, TZ, Locales, SSH Hardening) |
| `jarvis sys update` | Run system update (apt update/upgrade/clean/autoremove) |
| `jarvis sys adduser NAME` | Add a new user with sudo/ssh-key options |
| `jarvis sys clean-pc` | Run system cleanup (apt cleanup) |
| `jarvis sys upload FILE` | Upload a file to a transfer service for easy sharing |

### 🌐 net — Network & Security
Network tools and VPN management.

| Command | Description |
|---|---|
| `jarvis net vpn [NAME]` | Connect to a VPN server (reads from `secrets.json`) |
| `jarvis net speedtest` | Run a speed test (using `speedtest-cli`) |
| `jarvis net fast` | Run a fast.com speed test |

---

## ⚙️ Configuration

VPN credentials and other secrets are managed in `~/.jarvis/secrets.json` (or bundled during build).

```json
{
  "vpn": {
    "my-vpn": {
      "protocol": "anyconnect",
      "url": "vpn.example.com",
      "user": "username",
      "pass": "password"
    }
  }
}
```

---

## 🏗️ Build System

The project uses **PyInstaller** to produce a standalone binary.
Custom bash scripts (`scripts/legacy`) have been fully migrated to Python modules located in `src/jarvis/commands/`.

---
© 2026 Punsarn.asia
