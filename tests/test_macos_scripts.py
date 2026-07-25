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


def test_updater_does_not_overwrite_user_rules() -> None:
    text = (SCRIPTS / "update-macos.sh").read_text()
    assert 'cp "$project_dir/subscriptions.yaml"' not in text
    assert "validate-config" in text
    assert "current.rollback" in text


def test_user_facing_macos_scripts_are_english() -> None:
    for path in SCRIPTS.glob("*-macos.sh"):
        text = path.read_text()
        assert not any(
            "\u3040" <= character <= "\u30ff" or "\u4e00" <= character <= "\u9fff"
            for character in text
        ), path.name
