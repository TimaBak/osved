"""Static release-gate regression: never execute production deployment in tests."""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_staging_ssh_entrypoint_is_syntax_valid_and_restricted() -> None:
    path = ROOT / "deploy/osved-ssh-release.sh"
    result = subprocess.run(["bash", "-n", str(path)], check=False, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    source = path.read_text(encoding="utf-8")
    assert '[[ "$release_sha" =~ ^[a-f0-9]{40}$ ]]' in source
    assert 'refs/remotes/origin/main' in source
    assert "/usr/local/sbin/osved-root-deploy" in source
    assert "flock -n 9" in source
    assert "verify_health" in source


def test_ssh_workflow_has_main_success_guard_and_no_runner_root_access() -> None:
    source = (ROOT / ".github/workflows/staging-ssh.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    job = workflow["jobs"]["deploy"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["environment"] == "staging"
    assert "conclusion == 'success'" in job["if"]
    assert "head_branch == 'main'" in job["if"]
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert "StrictHostKeyChecking=yes" in source
    assert "OSVED_DEPLOY_KEY" in source
    assert "OSVED_KNOWN_HOSTS" in source
    assert "sudo " not in source
