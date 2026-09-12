from pathlib import Path

from fly.cli import systemd_unit


def test_systemd_unit_restarts_and_logs():
    u = systemd_unit(Path("/home/fly/FlyDeveloper"), "/home/fly/FlyDeveloper/.venv/bin/python", True, "fly",
                     Path("/home/fly/FlyDeveloper/data/fly-daemon.log"))
    assert "ExecStart=/home/fly/FlyDeveloper/.venv/bin/python /home/fly/FlyDeveloper/fly.py live --live" in u
    assert "Restart=always" in u and "User=fly" in u and "WantedBy=multi-user.target" in u
    assert "append:/home/fly/FlyDeveloper/data/fly-daemon.log" in u
    assert " --live" not in systemd_unit(Path("/x"), "python", False, "fly", Path("/x/log"))
