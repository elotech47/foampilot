"""Integration tests for Docker execution (require Docker running)."""

import pytest

pytestmark = pytest.mark.docker


@pytest.fixture
def docker_client():
    """Get Docker client if available, handling macOS Docker Desktop socket paths."""
    try:
        from foampilot.docker.client import _connect_docker
        client = _connect_docker()
        # Check if the OpenFOAM container is running
        from foampilot import config
        container = client.containers.get(config.OPENFOAM_CONTAINER)
        if container.status != "running":
            pytest.skip(f"Container {config.OPENFOAM_CONTAINER} is not running")
        return client
    except Exception as exc:
        pytest.skip(f"Docker not available: {exc}")


def test_docker_exec_echo(docker_client):
    """Verify we can exec into the container."""
    from foampilot.docker.client import DockerClient
    client = DockerClient(docker_sdk=docker_client)
    result = client.exec_command("echo 'foampilot_test_ok'")
    assert result["exit_code"] == 0
    assert "foampilot_test_ok" in result["stdout"]


def test_docker_openfoam_version(docker_client):
    """Verify OpenFOAM is available in the container."""
    from foampilot.docker.client import DockerClient
    from foampilot.version.registry import VersionRegistry

    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()

    client = DockerClient(docker_sdk=docker_client)
    result = client.exec_command(
        f"bash -c 'source /opt/openfoam{profile.VERSION}/etc/bashrc && foamVersion'"
    )
    assert result["exit_code"] == 0
