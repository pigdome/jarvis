# JARVIS

Tools for life hack — a CLI built with Typer for automation and productivity.

**Version:** v0.6.1

## Installation

### Download latest release (recommended)

```bash
mkdir -p ~/.local/bin
curl -L https://git.punsarn.com/apirak/jarvis/-/raw/main/jarvis \
  -o ~/.local/bin/jarvis && chmod +x ~/.local/bin/jarvis
```

### Build from source

```bash
git clone https://git.punsarn.com/apirak/jarvis.git jarvis
cd jarvis
bash build.sh
```

During build, you will be prompted to:
1. Bump the version (patch / minor / major / no change)
2. Create a git tag and push to GitLab (triggers CI to build and publish a release)
3. Install the binary to `~/.local/bin/jarvis`

## Usage

```
jarvis [COMMAND] [SUBCOMMAND] [OPTIONS]
```

```
jarvis help      # Show all commands in a tree view
jarvis version   # Show current version
```

## Commands

### 🌐 net — Network & Security

| Command | Description |
|---|---|
| `jarvis net vpn [NAME]` | Connect to a VPN server (reads from `secrets.json`) |
| `jarvis net speedtest` | Run a speed test (standard) |
| `jarvis net fast` | Run a fast.com speed test (Go binary) |

### 🏗️ sys — System & Infrastructure

| Command | Description |
|---|---|
| `jarvis sys adduser NICKNAME [--sudo] [--authkeys]` | Add a user from predefined nicknames |
| `jarvis sys clean-pc` | Run the Ubuntu system cleaner script |
| `jarvis sys setup-vim` | Link `.vimrc` from jarvis config |
| `jarvis sys deploy` | Run full JARVIS deployment/setup |
| `jarvis sys upload FILE [--host HOST]` | Upload a file to a transfer service |
| `jarvis sys keepass` | Open KeePass database with kpcli |
| `jarvis sys update` | Run apt update / upgrade / clean / autoremove |

### 🗄️ db — Database Utilities

| Command | Description |
|---|---|
| `jarvis db mysql` | Open MySQL client |
| `jarvis db psql` | Open PostgreSQL client |
| `jarvis db koha-dump INSTANCE` | Dump Koha database |
| `jarvis db koha-dump-fast INSTANCE` | Dump Koha database (fast method) |
| `jarvis db koha-info INSTANCE` | Show Koha instance info |
| `jarvis db koha-set-url INSTANCE URL` | Set Koha instance URL |

## Configuration

VPN credentials are stored in `secrets.json` at the project root:

```json
{
  "vpn": {
    "my-vpn": {
      "protocol": "anyconnect",
      "url": "vpn.example.com",
      "user": "username",
      "pass": "password",
      "cert": "hash:XXXXXX",
      "group": "group-name"
    }
  }
}
```

## Build from source

Requires Python 3.12+ and a virtual environment at `venv/` or `.venv/`.

```bash
bash build.sh
```

The build uses PyInstaller to produce a single executable at `dist/jarvis`.
