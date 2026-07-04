from pathlib import Path


def test_systemd_units_are_present() -> None:
    systemd = Path("packaging/systemd")

    assert (systemd / "privatetv.service").exists()
    assert (systemd / "privatetv-scan.timer").exists()
    assert (systemd / "privatetv-schedule.timer").exists()


def test_install_scripts_are_executable() -> None:
    assert Path("scripts/install-systemd.sh").stat().st_mode & 0o111
    assert Path("scripts/prepare-production-layout.sh").stat().st_mode & 0o111
