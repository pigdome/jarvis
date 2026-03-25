import json
from pathlib import Path


def migrate_vpn_secrets(perl_script_path: Path):
    """
    Primitive parser to extract secrets from the jarvis-vpn perl script.
    """
    import re
    if not perl_script_path.exists():
        return {}
    with open(perl_script_path, "r") as f:
        content = f.read()

    # Look for the servers hash
    match = re.search(r"sub servers \{(.*?)\};", content, re.DOTALL)
    if not match:
        return {}

    servers_content = match.group(1)

    # Extract each server block
    vpn_data = {}
    server_blocks = re.findall(
        r"(\w+) => \{(.*?)\s+\},", servers_content, re.DOTALL)

    for name, block in server_blocks:
        configs = {}
        for line in block.split("\n"):
            kv = re.search(r"(\w+)\s+=>\s+\"(.*?)\"", line)
            if kv:
                configs[kv.group(1)] = kv.group(2)
        vpn_data[name] = configs

    return {"vpn": vpn_data}


if __name__ == "__main__":
    from jarvis.config import save_secrets, JARVIS_ROOT
    # Path to legacy perl script
    legacy_vpn = JARVIS_ROOT / "scripts/legacy/jarvis-vpn"
    secrets = migrate_vpn_secrets(legacy_vpn)
    save_secrets(secrets)
    print("VPN secrets migrated to ~/.jarvis/secrets.json")
