"""Activation script must remain syntactically valid and fail closed."""
import subprocess
from pathlib import Path


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


def test_renewal_retry_only_accepts_osved_owned_vhost():
    script = (Path(__file__).parents[1] / 'deploy' / 'activate-osved-web.sh').read_text()
    assert 'Recognized existing OSVED reverse proxy' in script
    assert 'readlink "$ACTIVE"' in script
    assert "grep -Fq 'server_name osved.tima.biz;'" in script
    assert "grep -Fq 'proxy_pass http://127.0.0.1:18765;'" in script
    assert 'A different nginx vhost already exists' in script
    assert 'if [[ "$created_site" -eq 1 ]]' in script
