import typer
import subprocess
from typing import Optional
from jarvis.config import get_secrets, save_secrets, LEGACY_DIR

app = typer.Typer(
    help="Network and VPN related commands",
    no_args_is_help=True,
)


def get_vpn_names(ctx: typer.Context, incomplete: str):
    secrets = get_secrets()
    vpn_configs = secrets.get("vpn", {})
    return [name for name in vpn_configs.keys() if name.startswith(incomplete)]


@app.command(hidden=True)
def vpn(
    name: Optional[str] = typer.Argument(
        None,
        autocompletion=get_vpn_names,
        help="Name of the VPN server to connect to"
    )
):
    """
    Connect to a VPN server.
    """
    secrets = get_secrets()
    vpn_configs = secrets.get("vpn", {})

    if not name:
        if not vpn_configs:
            print("No VPN configurations found in secrets.json")
            return
        print("Available VPNs:")
        for vpn_name in sorted(vpn_configs.keys()):
            print(f" - {vpn_name}")
        return

    if name not in vpn_configs:
        print(f"Error: VPN '{name}' not found.")
        return

    conf = vpn_configs[name]
    protocol = conf.get("protocol", "").strip()
    url = conf.get("url", "").strip()
    user = conf.get("user", "").strip()
    password = conf.get("pass", "").strip()
    cert = conf.get("cert", "").strip()
    group = conf.get("group", "").strip()

    cmd = ["sudo", "openconnect", url]
    if protocol:
        cmd.extend(["--protocol", protocol])
    if cert:
        cmd.extend(["--servercert", cert])
    if user:
        cmd.extend(["--user", user])
    if group:
        cmd.extend(["--authgroup", group])

    import sys
    from rich.console import Console
    console_err = Console(stderr=True)

    full_cmd_parts = [f"echo '{password}'", "|", "sudo", "openconnect", url]
    if protocol:
        full_cmd_parts.extend(["--protocol", protocol])
    if cert:
        full_cmd_parts.extend(["--servercert", cert])
    if user:
        full_cmd_parts.extend(["--user", user])
    if group:
        full_cmd_parts.extend(["--authgroup", group])

    full_cmd = " ".join(full_cmd_parts)

    console_err.print(f"[yellow]Generated VPN command for {name} ({url}):[/yellow]")
    # Print the command to stdout so it can be piped
    print(full_cmd)


@app.command()
def speedtest():
    """
    Run a speed test using speedtest-cli.
    """
    subprocess.run(["speedtest-cli"])


@app.command()
def fast():
    """
    Run a fast.com speed test.
    """
    subprocess.run(["fast"])
