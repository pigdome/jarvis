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
| `jarvis db anonymize` | Replace personal data in a SQL dump stream or in a restored database |

#### Anonymize

`jarvis db anonymize` replaces personal data in a SQL dump stream, or in a
database that is already restored, according to a bundled profile (`koha`,
`dspace`, `room_reservation`, `linebrarian`) or your own TOML file. Keys,
foreign keys and every column the profile does not list are passed through
unchanged.

```bash
# stream: dump -> anonymize -> restore
pv dump.sql.gz | gunzip | jarvis db anonymize -p koha   | jarvis db mysql koha_spu
pv dump.sql.gz | gunzip | jarvis db anonymize -p dspace | jarvis db psql dspace8_nalt

# list the bundled profiles
jarvis db anonymize --list

# direct mode (database is already restored): asks you to type the
# database name to confirm; --yes skips the question (for scripts)
jarvis db anonymize -p koha -t mysql -d koha_spu
jarvis db anonymize -p koha -t mysql -d koha_spu --yes
jarvis db anonymize -p dspace -t psql -d dspace8_spu --dry-run   # print SQL only

# your own profile
jarvis db anonymize --profile-file ./my-profile.toml < dump.sql > anonymized.sql
```

Run the restore side under `set -o pipefail` so a failed anonymize stops the
pipeline instead of restoring a partial dump.

Output is pseudonymized test data — still handle under PDPA s.37.

### 🏗️ sys — Infrastructure & System
System-level management and setup.

| Command | Description |
|---|---|
| `jarvis sys init` | **Root only.** Full server setup (Apt, TZ, Locales, SSH Hardening) |
| `jarvis sys update` | Run system update (apt update/upgrade/clean/autoremove) |
| `jarvis sys adduser NAME` | Add a new user with sudo/ssh-key options |
| `jarvis sys clean-pc` | Clean a Linux PC (apt, Trash, thumbnails, caches, journals, Flatpak/Snap; optional Docker) |
| `jarvis sys upload FILE` | Upload a file to a transfer service for easy sharing |
| `jarvis sys orca setup [PATH...]` | Turn projects into Orca orchestration projects: install `orchestration` + `orca-cli` skills locally and add the managed CLAUDE.md section (`--all-orca-repos`, `--agents`, `--force`, `--dry-run`) |
| `jarvis sys orca status [PATH...]` | Show per project whether skills are installed and the CLAUDE.md section is present / up to date / edited / legacy |
| `jarvis sys orca remove [PATH...]` | Remove the CLAUDE.md section and the two skill dirs (`--purge` also cleans `skills-lock.json`) |
| `jarvis sys skill-audit [PATH]` | Audit agent skills with NVIDIA SkillSpector (`--llm`, `--workers`, `--min-severity`, `--format`, `--fail-on`, `--include-builtin`) |

#### Skill audit

`jarvis sys skill-audit [PATH]` scans agent skills with
[NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector). `PATH` can be a root
directory to discover under (default `~`), a single skill directory, or a `SKILL.md`
file.

```bash
jarvis sys skill-audit ~/.claude/skills --no-llm
jarvis sys skill-audit ~/.claude/skills --min-severity high --fail-on critical
jarvis sys skill-audit ~/.claude/skills --format json
```

Reports are written to `~/.jarvis/reports/skill-audit-<timestamp>/` (`summary.json`,
`summary.md`, and one JSON report per skill). SkillSpector is auto-installed with
`uv tool install git+https://github.com/NVIDIA/skillspector.git` on first use.
Vendor/builtin trees are skipped unless `--include-builtin` is passed.

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
