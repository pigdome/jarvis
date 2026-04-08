import typer
import subprocess
from typing import Optional
from jarvis.config import get_secrets, save_secrets, LEGACY_DIR, CONFIG_DIR

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
    vpn_type = conf.get("type", "openconnect")
    password = conf.get("pass", "").strip()

    from rich.console import Console
    console_err = Console(stderr=True)

    if vpn_type == "openvpn":
        from pathlib import Path
        filename = conf.get("config", "").strip()
        search_paths = [CONFIG_DIR / filename, Path("/etc/jarvis") / filename]
        config_path = next((p for p in search_paths if p.exists()), None)
        if not config_path:
            print(f"Error: '{filename}' not found in config directories.")
            return
        full_cmd = f"echo '{password}' | sudo openvpn --config {str(config_path)} --auth-user-pass /dev/stdin"
        console_err.print(f"[yellow]Connecting to VPN {name} ({config_path})...[/yellow]")
        subprocess.run(full_cmd, shell=True)
        return

    protocol = conf.get("protocol", "").strip()
    url = conf.get("url", "").strip()
    user = conf.get("user", "").strip()
    cert = conf.get("cert", "").strip()
    group = conf.get("group", "").strip()

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

    console_err.print(f"[yellow]Connecting to VPN {name} ({url})...[/yellow]")
    subprocess.run(full_cmd, shell=True)


@app.command()
def speedtest():
    """
    Run a speed test using speedtest-cli (Python implementation).
    """
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    import speedtest as st_lib
    
    console = Console()
    console.print("🚀 [bold cyan]Starting Speedtest.net...[/bold cyan]")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            # 1. Finding server
            progress.add_task(description="🔍 Finding best server...", total=None)
            s = st_lib.Speedtest()
            s.get_best_server()
            
            # 2. Download
            task_dl = progress.add_task(description="📥 Testing Download speed...", total=None)
            s.download()
            progress.update(task_dl, completed=True)
            
            # 3. Upload
            task_ul = progress.add_task(description="📤 Testing Upload speed...", total=None)
            s.upload()
            progress.update(task_ul, completed=True)
            
            results = s.results.dict()
            
        console.print(f"✅ [bold green]Speedtest Complete![/bold green]")
        console.print(f"  • [bold]Host     :[/bold] {results['server']['host']} ({results['server']['name']})")
        console.print(f"  • [bold]Download :[/bold] [cyan]{results['download'] / 1_000_000:.2f} Mbps[/cyan]")
        console.print(f"  • [bold]Upload   :[/bold] [cyan]{results['upload'] / 1_000_000:.2f} Mbps[/cyan]")
        console.print(f"  • [bold]Ping     :[/bold] [yellow]{results['ping']:.2f} ms[/yellow]")
        
    except Exception as e:
        console.print(f"❌ [red]Speedtest failed: {e}[/red]")


@app.command()
def fast():
    """
    Run a fast.com speed test (Python implementation).
    """
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    import subprocess
    import json
    
    console = Console()
    console.print("🚀 [bold cyan]Starting Fast.com (Netflix)...[/bold cyan]")
    
    # fast-cli (python version) often just uses a helper. 
    # Since fastcli is a bit unstable, we'll try to use the library interface
    try:
        from fastcli import fastcli
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="📥 Measuring download speed...", total=None)
            # fastcli.run() returns the speed in Mbps as a float
            speed = fastcli.run()
            
        console.print(f"✅ [bold green]Fast.com Complete![/bold green]")
        console.print(f"  • [bold]Download :[/bold] [cyan]{speed:.2f} Mbps[/cyan]")
        
    except ImportError:
        console.print("[yellow]⚠️  fastcli library not found. Falling back to system command...[/yellow]")
        subprocess.run(["fast"])
    except Exception as e:
        console.print(f"❌ [red]Fast.com test failed: {e}[/red]")
