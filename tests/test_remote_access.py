from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_cloudflared_launcher_is_fail_closed_and_local_only():
    script = (ROOT / "tools/macos/run_cloudflared_tunnel.sh").read_text()
    assert "tunnel run" in script
    assert "127.0.0.1:8000" in script
    assert "CLOUDFLARED_CONFIG" in script
    assert "CLOUDFLARED_TOKEN_FILE" in script
    assert "must have mode 600 or 640" in script
    assert "--token \"" not in script
    assert "--token-file" in script
    assert "/opt/homebrew/bin/cloudflared" in script


def test_cloudflared_launch_agent_restarts_tunnel_without_exposing_agent_port():
    plist = (ROOT / "mac_gateway/launchd/com.calendaragent.cloudflared.plist.template").read_text()
    assert "RunAtLoad" in plist
    assert "KeepAlive" in plist
    assert "run_cloudflared_tunnel.sh" in plist
    assert "127.0.0.1:8000" not in plist


def test_cloudflared_example_routes_only_to_loopback():
    config = (ROOT / "tools/macos/cloudflared-config.example.yml").read_text()
    assert "service: http://127.0.0.1:8000" in config
    assert "service: http_status:404" in config
    assert "REPLACE_ME" in config


def test_agent_service_fails_before_registration_without_config():
    script = (ROOT / "tools/macos/agent_server_service.sh").read_text()
    assert "Missing readable configuration" in script
    assert "launchctl bootstrap" in script
