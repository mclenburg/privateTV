from __future__ import annotations

from pathlib import Path

from privatetv.config import settings_from_mapping
from privatetv.domain.models import MediaAsset
from privatetv.spikes import DvdConcatSpikeRunner, TvheadendProbeServer, build_seek_spike_report


def _settings(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {"directories": [str(media_dir)]},
            "schedule": {"days_ahead": 5, "minimum_days_ahead": 3, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "shuffle_no_repeat"},
            "streaming": {"max_parallel_streams": 4, "output_container": "mpegts", "prefer_stream_copy": True, "transcode_when_needed": False, "ffmpeg_path": "/usr/bin/ffmpeg", "ffprobe_path": "/usr/bin/ffprobe", "accepted_seek_tolerance_seconds": 10},
            "database": {"path": str(tmp_path / "privatetv.sqlite3")},
        }
    )


def test_seek_spike_report_documents_keyframe_tolerance(tmp_path: Path) -> None:
    report = build_seek_spike_report(_settings(tmp_path), offset_seconds=42.5)

    assert report.offset_seconds == 42.5
    assert report.accepted_tolerance_seconds == 10
    assert "-ss" in report.command
    assert "copy" in report.command
    assert "keyframe-aligned" in report.as_text()


def test_dvd_concat_spike_builds_demuxer_and_protocol_candidates(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = tmp_path / "VTS_01_1.VOB"
    second = tmp_path / "VTS_01_2.VOB"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    assets = (
        MediaAsset(id=None, media_item_id=1, asset_order=1, path=first, role="segment"),
        MediaAsset(id=None, media_item_id=1, asset_order=2, path=second, role="segment"),
    )

    result = DvdConcatSpikeRunner(settings).run(assets, execute=False)

    assert len(result.candidates) == 2
    assert result.candidates[0].name == "concat-demuxer-genpts"
    assert "+genpts" in result.candidates[0].command
    assert result.candidates[1].name == "concat-protocol"
    assert any(part.startswith("concat:") for part in result.candidates[1].command)
    assert result.attempts == ()
    for candidate in result.candidates:
        if candidate.temp_file is not None:
            candidate.temp_file.unlink(missing_ok=True)


def test_tvheadend_probe_state_counts_connections() -> None:
    server = TvheadendProbeServer(host="127.0.0.1", port=9998)

    server.state.opened("client-a")
    server.state.opened("client-b")
    server.state.closed("client-a")

    status = server.state.as_dict()
    assert status["active_connections"] == 1
    assert status["total_connections"] == 2
    assert status["max_concurrent_connections"] == 2
