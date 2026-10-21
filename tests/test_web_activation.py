"""Activation script must remain syntactically valid and fail closed."""
from pathlib import Path
import subprocess


def test_https_activation_shell_is_valid():
    script = Path(__file__).parents[1] / "deploy" / "activate-osved-web.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    content = script.read_text(encoding="utf-8")
    assert "127.0.0.1:18765/healthz" in content
    assert "nginx -t" in content
    assert "OSVED_WEB_URL=https://osved.tima.biz" in content
    assert "HERMES_IPV4=31.76.77.87" in content
    assert "curl --fail" in content
    assert "cat /opt/osved/app/.env" not in content
