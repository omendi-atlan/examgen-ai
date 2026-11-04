"""Live integration tests against the ClamAV service container in CI."""

import socket
import time

import pytest
from app.core.config import get_settings
from app.services.malware_scanning import MalwareDetectedError, scan_file


@pytest.fixture
def live_clamav(tmp_path):
    settings = get_settings()
    previous = (
        settings.malware_scan_enabled,
        settings.clamav_host,
        settings.clamav_port,
        settings.clamav_timeout_seconds,
    )
    settings.malware_scan_enabled = True
    settings.clamav_host = "127.0.0.1"
    settings.clamav_port = 3310
    settings.clamav_timeout_seconds = 10

    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 3310), timeout=2):
                break
        except OSError:
            time.sleep(3)
    else:
        pytest.fail("ClamAV service did not become reachable within four minutes.")

    yield tmp_path
    (
        settings.malware_scan_enabled,
        settings.clamav_host,
        settings.clamav_port,
        settings.clamav_timeout_seconds,
    ) = previous


def test_live_clamav_accepts_clean_file_and_detects_eicar(live_clamav) -> None:
    clean = live_clamav / "clean.txt"
    clean.write_text("Ordinary academic course notes.", encoding="utf-8")
    assert scan_file(clean) == {"enabled": True, "status": "clean"}

    eicar = live_clamav / "eicar.com"
    eicar.write_text(
        "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",
        encoding="ascii",
    )
    with pytest.raises(MalwareDetectedError):
        scan_file(eicar)
