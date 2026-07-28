from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def test_installer_uses_setup_and_never_writes_plaintext_secrets() -> None:
    text = (SCRIPTS / "install-macos.sh").read_text()
    assert "setup notifications" in text
    assert "SMTP_PASSWORD=" not in text
    assert "DISCORD_WEBHOOK=$" not in text
    assert "brew install" not in text
    assert "astral.sh/uv/install.sh" in text
    assert ",," not in text  # macOS ships Bash 3.2, which lacks ${value,,}
    assert 'grep -q "state = running"' in text


def test_updater_does_not_overwrite_user_rules() -> None:
    text = (SCRIPTS / "update-macos.sh").read_text()
    assert 'cp "$project_dir/subscriptions.yaml"' not in text
    assert "validate-config" in text
    assert "current.rollback" in text
    assert '--subscriptions "$candidate/subscriptions.yaml" setup migrate' in text
    assert 'cp "$backup_dir/subscriptions.yaml" "$runtime_dir/subscriptions.yaml"' in text
    assert 'cp "$backup_dir/.env" "$runtime_dir/.env"' in text
    assert 'cp "$candidate/.env" "$runtime_dir/.env.next"' in text
    assert 'grep -q "state = running"' in text


def test_user_facing_macos_scripts_are_english() -> None:
    for path in SCRIPTS.glob("*-macos.sh"):
        text = path.read_text()
        assert not any(
            "\u3040" <= character <= "\u30ff" or "\u4e00" <= character <= "\u9fff"
            for character in text
        ), path.name


def test_installation_smoke_test_is_isolated() -> None:
    text = (SCRIPTS / "smoke-test-install.sh").read_text()
    assert "mktemp -d" in text
    assert "Library/Application Support" not in text
    assert "launchctl" not in text
    assert "validate-config" in text
    assert "setup list" in text
