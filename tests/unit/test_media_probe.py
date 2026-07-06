from __future__ import annotations

from pathlib import Path

import pytest

from privatetv.media.probe import ProbeError, probe_result_from_payload


def test_probe_result_extracts_duration_and_codecs(tmp_path: Path) -> None:
    media_file = tmp_path / "Demo.Movie.mp4"
    media_file.write_bytes(b"not a real video for this unit test")

    result = probe_result_from_payload(
        media_file,
        {
            "format": {"duration": "12.345", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
    )

    assert result.duration_seconds == 12.345
    assert result.container == "mov"
    assert result.video_codec == "h264"
    assert result.audio_codec == "aac"
    assert result.file_size_bytes == media_file.stat().st_size


def test_probe_result_rejects_missing_duration(tmp_path: Path) -> None:
    media_file = tmp_path / "broken.mp4"
    media_file.write_bytes(b"x")

    with pytest.raises(ProbeError, match="no duration"):
        probe_result_from_payload(media_file, {"format": {}, "streams": []})


def test_packet_count_duration_from_payload_uses_read_packets_and_frame_rate() -> None:
    from privatetv.media.probe import packet_count_duration_from_payload

    duration = packet_count_duration_from_payload(
        {
            "streams": [
                {
                    "nb_read_packets": "100896",
                    "r_frame_rate": "25/1",
                    "avg_frame_rate": "25/1",
                }
            ]
        }
    )

    assert duration == pytest.approx(4035.84)
