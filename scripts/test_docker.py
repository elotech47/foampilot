#!/usr/bin/env python3
"""FoamPilot Docker connectivity test.

Runs a graduated series of checks to verify that the OpenFOAM container
is reachable, the volume mount is working, and OpenFOAM commands execute
correctly. No Claude API key needed.

Usage:
    uv run python scripts/test_docker.py
    uv run python scripts/test_docker.py --case-dir /home/openfoam/cases
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── Rich console setup ──────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    console = Console()
    RICH = True
except ImportError:
    RICH = False

    class Console:  # type: ignore
        def print(self, *a, **kw): print(*a)
        def rule(self, *a, **kw): print("─" * 60)
    console = Console()


def header(text: str) -> None:
    if RICH:
        console.rule(f"[bold cyan]{text}[/]")
    else:
        print(f"\n{'─'*60}\n{text}\n{'─'*60}")


def ok(label: str, detail: str = "") -> None:
    msg = f"[bold green]  PASS[/]  {label}"
    if detail:
        msg += f"  [dim]{detail}[/]"
    console.print(msg)


def fail(label: str, detail: str = "") -> None:
    msg = f"[bold red]  FAIL[/]  {label}"
    if detail:
        msg += f"\n         [red]{detail}[/]"
    console.print(msg)


def info(text: str) -> None:
    console.print(f"  [dim]{text}[/]")


def abort(reason: str) -> None:
    console.print(f"\n[bold red]ABORTED:[/] {reason}\n")
    sys.exit(1)


# ───────────────────────────────────────────────────────────────────────────

def test_docker_connection() -> object:
    """Step 1 – Connect to the Docker daemon."""
    header("Step 1: Docker daemon connection")
    try:
        from foampilot.docker.client import _connect_docker
        client = _connect_docker()
        client.ping()
        ok("Docker daemon reachable")
        info(f"Server version: {client.version()['Version']}")
        return client
    except Exception as exc:
        fail("Cannot connect to Docker daemon", str(exc))
        abort(
            "Make sure Docker Desktop is running. "
            "On macOS the socket is at ~/.docker/run/docker.sock."
        )


def test_container_running(client, container_name: str) -> object:
    """Step 2 – Confirm the OpenFOAM container is running."""
    header(f"Step 2: Container '{container_name}' status")
    try:
        container = client.containers.get(container_name)
    except Exception as exc:
        fail(f"Container '{container_name}' not found", str(exc))
        abort(
            f"Run:  docker-compose up -d\n"
            f"Then check:  docker ps"
        )

    status = container.status
    if status != "running":
        fail(f"Container status = {status!r} (expected 'running')")
        abort("Run:  docker-compose up -d")

    ok(f"Container is running", f"id={container.short_id}")
    info(f"Image: {container.image.tags[0] if container.image.tags else container.image.short_id}")
    return container


def test_basic_exec(container) -> None:
    """Step 3 – Run a trivial command to confirm exec works."""
    header("Step 3: Basic exec (echo)")
    result = container.exec_run("echo foampilot_test_ok", demux=True)
    stdout = (result.output[0] or b"").decode().strip()
    if result.exit_code == 0 and "foampilot_test_ok" in stdout:
        ok("exec_run works", f"got: {stdout!r}")
    else:
        fail("exec_run failed", f"exit={result.exit_code}, stdout={stdout!r}")


def test_openfoam_env(container, version: str) -> None:
    """Step 4 – Source the OpenFOAM bashrc and run foamVersion."""
    header(f"Step 4: OpenFOAM v{version} environment")
    bashrc = f"/opt/openfoam{version}/etc/bashrc"

    # Check bashrc exists
    r = container.exec_run(f"test -f {bashrc}", demux=True)
    if r.exit_code != 0:
        fail(f"bashrc not found at {bashrc}")
        info("The image may be for a different OpenFOAM version.")
        return
    ok(f"bashrc found", bashrc)

    # Source and run foamVersion
    cmd = f"bash -c 'source {bashrc} && foamVersion'"
    r = container.exec_run(cmd, demux=True)
    stdout = (r.output[0] or b"").decode().strip()
    stderr = (r.output[1] or b"").decode().strip()
    if r.exit_code == 0:
        ok("foamVersion executed", stdout or "(no output)")
    else:
        fail("foamVersion failed", stderr or stdout)

    # Check that a key solver binary exists
    solver_cmd = f"bash -c 'source {bashrc} && which simpleFoam'"
    r = container.exec_run(solver_cmd, demux=True)
    path = (r.output[0] or b"").decode().strip()
    if r.exit_code == 0 and path:
        ok("simpleFoam binary found", path)
    else:
        fail("simpleFoam not found after sourcing bashrc")


def test_volume_mount(container, host_cases_dir: Path, container_cases_dir: str) -> None:
    """Step 5 – Verify the volume mount (host ↔ container)."""
    header("Step 5: Volume mount (host ↔ container)")
    sentinel_name = ".foampilot_mount_test"

    # Write a file on the host
    sentinel_host = host_cases_dir / sentinel_name
    try:
        host_cases_dir.mkdir(parents=True, exist_ok=True)
        sentinel_host.write_text("mount_ok")
    except Exception as exc:
        fail("Cannot write to host cases dir", str(exc))
        return

    # Check it's visible in the container
    container_path = f"{container_cases_dir}/{sentinel_name}"
    r = container.exec_run(f"cat {container_path}", demux=True)
    content = (r.output[0] or b"").decode().strip()
    sentinel_host.unlink(missing_ok=True)

    if r.exit_code == 0 and content == "mount_ok":
        ok("Host→container visible", f"{host_cases_dir} → {container_cases_dir}")
    else:
        fail(
            "Host files NOT visible in container",
            f"Container path: {container_path}\n"
            f"         Make sure docker-compose.yml mounts {host_cases_dir} at {container_cases_dir}",
        )
        return

    # Write from container, check on host
    host_write_path = host_cases_dir / ".foampilot_container_write"
    r = container.exec_run(
        f"bash -c 'echo container_write_ok > {container_cases_dir}/.foampilot_container_write'",
        demux=True,
    )
    if r.exit_code == 0 and host_write_path.exists():
        content = host_write_path.read_text().strip()
        host_write_path.unlink(missing_ok=True)
        ok("Container→host write works", f"read back: {content!r}")
    else:
        host_write_path.unlink(missing_ok=True)
        fail("Container cannot write to mounted volume")


def test_blockmesh(
    container,
    host_cases_dir: Path,
    container_cases_dir: str,
    version: str,
) -> None:
    """Step 6 – Run blockMesh on a minimal 2D cavity case."""
    header("Step 6: blockMesh end-to-end")

    test_case_name = "foampilot_docker_test"
    host_case = host_cases_dir / test_case_name
    container_case = f"{container_cases_dir}/{test_case_name}"

    # Clean up any leftover from a previous run
    if host_case.exists():
        shutil.rmtree(host_case)

    # Write a minimal cavity blockMeshDict
    (host_case / "system").mkdir(parents=True)
    (host_case / "constant").mkdir(parents=True)
    (host_case / "0").mkdir(parents=True)

    (host_case / "system" / "controlDict").write_text(
        'FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }\n'
        'application icoFoam;\nstartFrom startTime;\nstartTime 0;\n'
        'stopAt endTime;\nendTime 0.1;\ndeltaT 0.005;\nwriteControl timeStep;\nwriteInterval 20;\n'
    )

    (host_case / "system" / "blockMeshDict").write_text(
        'FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }\n'
        'scale 0.1;\n'
        'vertices\n(\n'
        '    (0 0 0) (1 0 0) (1 1 0) (0 1 0)\n'
        '    (0 0 0.1) (1 0 0.1) (1 1 0.1) (0 1 0.1)\n'
        ');\n'
        'blocks\n(\n'
        '    hex (0 1 2 3 4 5 6 7) (20 20 1) simpleGrading (1 1 1)\n'
        ');\n'
        'boundary\n(\n'
        '    movingWall { type wall; faces ((3 7 6 2)); }\n'
        '    fixedWalls  { type wall; faces ((0 4 7 3) (2 6 5 1) (1 5 4 0)); }\n'
        '    frontAndBack { type empty; faces ((0 3 2 1) (4 5 6 7)); }\n'
        ');\n'
    )

    info(f"Created test case at {host_case}")
    info(f"Running: blockMesh in container at {container_case}")

    bashrc = f"/opt/openfoam{version}/etc/bashrc"
    cmd = f"bash -c 'source {bashrc} && cd {container_case} && blockMesh'"
    r = container.exec_run(cmd, demux=True)
    stdout = (r.output[0] or b"").decode()
    stderr = (r.output[1] or b"").decode()

    if r.exit_code == 0:
        ok("blockMesh succeeded", f"exit_code=0")
        # Check that constant/polyMesh was created
        poly_mesh = host_case / "constant" / "polyMesh"
        if poly_mesh.exists():
            ok("constant/polyMesh created on host", str(poly_mesh))
        else:
            fail("constant/polyMesh NOT found on host (mount issue?)")
        # Show last few lines
        tail = [l for l in stdout.splitlines() if l.strip()][-5:]
        info("blockMesh output (tail):")
        for line in tail:
            info(f"  {line}")
    else:
        fail("blockMesh failed", f"exit_code={r.exit_code}")
        if stderr:
            info("stderr:")
            for line in stderr.splitlines()[-10:]:
                info(f"  {line}")
        if stdout:
            info("stdout tail:")
            for line in stdout.splitlines()[-10:]:
                info(f"  {line}")

    # Clean up test case
    shutil.rmtree(host_case, ignore_errors=True)
    info(f"Test case cleaned up.")


def print_summary(results: dict[str, bool]) -> None:
    """Print a final pass/fail table."""
    header("Summary")
    if RICH:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Test", style="cyan")
        table.add_column("Result", justify="center")
        for name, passed in results.items():
            icon = "[bold green]PASS[/]" if passed else "[bold red]FAIL[/]"
            table.add_row(name, icon)
        console.print(table)
    else:
        for name, passed in results.items():
            status = "PASS" if passed else "FAIL"
            print(f"  {status}  {name}")

    all_passed = all(results.values())
    if all_passed:
        console.print("\n[bold green]All checks passed. Docker is ready for FoamPilot.[/]\n")
    else:
        console.print("\n[bold red]Some checks failed. Fix the issues above before running FoamPilot.[/]\n")


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FoamPilot Docker connectivity test")
    parser.add_argument(
        "--container", default="foampilot-openfoam",
        help="OpenFOAM container name (default: foampilot-openfoam)",
    )
    parser.add_argument(
        "--version", default="11",
        help="OpenFOAM version (default: 11)",
    )
    parser.add_argument(
        "--host-cases-dir",
        default=str(Path(__file__).parent.parent / "cases"),
        help="Host-side cases directory (default: ./cases)",
    )
    parser.add_argument(
        "--container-cases-dir", default="/home/openfoam/cases",
        help="Container-side cases directory (default: /home/openfoam/cases)",
    )
    args = parser.parse_args()

    host_cases_dir = Path(args.host_cases_dir)

    if RICH:
        console.print(Panel.fit(
            "[bold]FoamPilot — Docker Connectivity Test[/]\n"
            f"Container:  [cyan]{args.container}[/]\n"
            f"OpenFOAM:   [cyan]v{args.version}[/]\n"
            f"Host cases: [cyan]{host_cases_dir}[/]\n"
            f"Ctr cases:  [cyan]{args.container_cases_dir}[/]",
            border_style="cyan",
        ))
    else:
        print("FoamPilot — Docker Connectivity Test")

    results: dict[str, bool] = {}

    # Step 1
    client = test_docker_connection()
    results["Docker daemon connection"] = True

    # Step 2
    container = test_container_running(client, args.container)
    results["Container running"] = True

    # Step 3
    try:
        test_basic_exec(container)
        results["Basic exec (echo)"] = True
    except Exception as exc:
        fail("Basic exec exception", str(exc))
        results["Basic exec (echo)"] = False

    # Step 4
    try:
        test_openfoam_env(container, args.version)
        results["OpenFOAM environment"] = True
    except Exception as exc:
        fail("OpenFOAM env exception", str(exc))
        results["OpenFOAM environment"] = False

    # Step 5
    try:
        test_volume_mount(container, host_cases_dir, args.container_cases_dir)
        results["Volume mount (host↔container)"] = True
    except Exception as exc:
        fail("Volume mount exception", str(exc))
        results["Volume mount (host↔container)"] = False

    # Step 6
    try:
        test_blockmesh(container, host_cases_dir, args.container_cases_dir, args.version)
        results["blockMesh end-to-end"] = True
    except Exception as exc:
        fail("blockMesh exception", str(exc))
        results["blockMesh end-to-end"] = False

    print_summary(results)


if __name__ == "__main__":
    main()
