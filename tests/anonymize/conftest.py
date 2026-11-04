"""Shared fixtures for the anonymize tests.

``MYSQL_DUMP`` and ``PG_DUMP`` are synthetic dumps produced with the real dump
tools (``mariadb-dump`` from ``mariadb:11`` and ``pg_dump`` from
``postgres:16``).  Regenerate them with
``tests/fixtures/anonymize/make_fixtures.sh``; no production data is involved.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "anonymize"
MYSQL_DUMP = FIXTURE_DIR / "mysql_dump.sql"
PG_DUMP = FIXTURE_DIR / "pg_dump.sql"

MARIADB_IMAGE = "mariadb:11"
PG_IMAGE = "postgres:16"
PASSWORD = "test"
START_TIMEOUT = 120.0

_MARIADB_READY = "MariaDB init process done. Ready for start up."
_PG_READY = "PostgreSQL init process complete; ready for start up."


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "docker: needs a throwaway mariadb:11 or postgres:16 container"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    marked = [item for item in items if "docker" in item.keywords]
    if not marked:
        return
    if shutil.which("docker") is None or _run(["docker", "info"]).returncode != 0:
        skip = pytest.mark.skip(reason="docker is not available")
        for item in marked:
            item.add_marker(skip)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def _ensure_image(image: str) -> None:
    if _run(["docker", "image", "inspect", image]).returncode == 0:
        return
    _run(["docker", "pull", image])
    if _run(["docker", "image", "inspect", image]).returncode != 0:
        pytest.skip(f"docker image {image!r} is not available")


def _start(image: str, name: str, env: dict[str, str]) -> None:
    cmd = ["docker", "run", "-d", "--name", name]
    for key, value in env.items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.append(image)
    result = _run(cmd)
    if result.returncode != 0:
        pytest.fail(f"cannot start {image}: {result.stderr.strip()}")


def _logs(name: str) -> str:
    result = _run(["docker", "logs", name])
    return result.stdout + result.stderr


def _wait_ready(
    name: str, marker: str, probe: list[str], description: str
) -> None:
    """Wait for the entrypoint's temporary server to hand over to the real one.

    Both official images serve a temporary socket-only instance while they
    initialise, so a query alone can succeed too early; the log marker for
    "init done" plus a working query is what proves the final server is up.
    """
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        probe_ok = _run(["docker", "exec", name, *probe]).returncode == 0
        if marker in _logs(name) and probe_ok:
            return
        time.sleep(1.0)
    pytest.fail(
        f"{description} did not become ready in {START_TIMEOUT:.0f}s:\n"
        + "\n".join(_logs(name).splitlines()[-30:])
    )


def _stop(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest.fixture(scope="session")
def docker_available() -> bool:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is not installed")
    if _run(["docker", "info"]).returncode != 0:
        pytest.skip("docker is not available")
    return True


@pytest.fixture(scope="session")
def mariadb_container(docker_available: bool) -> list[str]:
    """Client command list: ``docker exec -i <name> mariadb -uroot -ptest``."""
    _ensure_image(MARIADB_IMAGE)
    name = f"jarvis-anon-mysql-{uuid.uuid4().hex[:8]}"
    _start(MARIADB_IMAGE, name, {"MARIADB_ROOT_PASSWORD": PASSWORD})
    try:
        _wait_ready(
            name,
            _MARIADB_READY,
            ["mariadb", "-uroot", f"-p{PASSWORD}", "-e", "SELECT 1"],
            "mariadb",
        )
        yield ["docker", "exec", "-i", name, "mariadb", "-uroot", f"-p{PASSWORD}"]
    finally:
        _stop(name)


@pytest.fixture(scope="session")
def pg_container(docker_available: bool) -> list[str]:
    """Client command list: ``docker exec -i <name> psql -U postgres -v ON_ERROR_STOP=1``."""
    _ensure_image(PG_IMAGE)
    name = f"jarvis-anon-pg-{uuid.uuid4().hex[:8]}"
    _start(PG_IMAGE, name, {"POSTGRES_PASSWORD": PASSWORD})
    try:
        _wait_ready(
            name,
            _PG_READY,
            ["psql", "-U", "postgres", "-d", "postgres", "-c", "SELECT 1"],
            "postgres",
        )
        yield [
            "docker",
            "exec",
            "-i",
            name,
            "psql",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
        ]
    finally:
        _stop(name)


def engine_of(client: list[str]) -> str:
    """Return ``mysql`` or ``psql`` for a client command list from a fixture."""
    for part in client:
        program = Path(part).name
        if program in {"mariadb", "mysql"}:
            return "mysql"
        if program == "psql":
            return "psql"
    raise ValueError(f"not a mysql/psql client command: {client!r}")


def create_db(client: list[str], name: str) -> None:
    """(Re)create an empty database through a client command from a fixture."""
    engine = engine_of(client)
    if engine == "mysql":
        sql = f"DROP DATABASE IF EXISTS `{name}`; CREATE DATABASE `{name}`;"
        cmd = [*client, "-e", sql]
    else:
        cmd = [
            *client,
            "-d",
            "postgres",
            "-c",
            f'DROP DATABASE IF EXISTS "{name}"',
            "-c",
            f'CREATE DATABASE "{name}"',
        ]
    result = _run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"cannot create database {name}: {result.stderr.strip()}")
