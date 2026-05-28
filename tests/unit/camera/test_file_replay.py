from pathlib import Path

import cv2
import numpy as np
import pytest

from curbcam.camera.file_replay import FileReplaySource


def _write_jpgs(dir_: Path, count: int) -> None:
    for i in range(count):
        img = np.full((120, 160, 3), fill_value=10 + i, dtype=np.uint8)
        cv2.imwrite(str(dir_ / f"{i:04d}.jpg"), img)


def test_file_replay_reads_frames_in_order(tmp_path: Path) -> None:
    _write_jpgs(tmp_path, count=3)
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    cam.open()
    try:
        frames = []
        while (got := cam.read()) is not None:
            frames.append(got)
        assert len(frames) == 3
        # Pixel values increase by 1 per frame, so means do too.
        means = [float(f[0].mean()) for f in frames]
        assert means[0] < means[1] < means[2]
    finally:
        cam.close()


def test_file_replay_resolution_matches_first_frame(tmp_path: Path) -> None:
    _write_jpgs(tmp_path, count=1)
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    cam.open()
    try:
        assert cam.resolution == (160, 120)
    finally:
        cam.close()


def test_file_replay_loops_when_loop_true(tmp_path: Path) -> None:
    _write_jpgs(tmp_path, count=2)
    cam = FileReplaySource(tmp_path, fps_target=30.0, loop=True)
    cam.open()
    try:
        got = [cam.read() for _ in range(5)]
        assert all(f is not None for f in got)
    finally:
        cam.close()


def test_file_replay_read_before_open_raises(tmp_path: Path) -> None:
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    with pytest.raises(RuntimeError):
        cam.read()


def test_file_replay_raises_on_empty_directory(tmp_path: Path) -> None:
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    with pytest.raises(FileNotFoundError):
        cam.open()


def test_file_replay_close_resets_state_for_rewind(tmp_path: Path) -> None:
    """After close() and re-open(), reading starts from the first frame again."""
    _write_jpgs(tmp_path, count=3)
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    cam.open()
    first = cam.read()
    cam.read()
    cam.read()
    cam.close()
    cam.open()
    first_after_rewind = cam.read()
    cam.close()
    assert first is not None and first_after_rewind is not None
    # Same first frame seen on both opens — content identical.
    np.testing.assert_array_equal(first[0], first_after_rewind[0])


def test_file_replay_picks_up_uppercase_extensions(tmp_path: Path) -> None:
    """Case-insensitive suffix matching for portability on Linux filesystems."""
    img = np.full((10, 10, 3), 100, dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "frame.JPG"), img)
    cv2.imwrite(str(tmp_path / "frame.PNG"), img)
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    cam.open()
    try:
        assert cam.read() is not None  # at least one frame discovered
    finally:
        cam.close()


def test_file_replay_skips_undecodable_middle_frame_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A corrupt middle frame must NOT be confused with source exhaustion."""
    import logging

    import cv2
    import numpy as np

    # Three frames: good, corrupt-stub, good
    cv2.imwrite(str(tmp_path / "0001.jpg"), np.full((10, 10, 3), 50, dtype=np.uint8))
    (tmp_path / "0002.jpg").write_bytes(b"this is not a jpeg")
    cv2.imwrite(str(tmp_path / "0003.jpg"), np.full((10, 10, 3), 200, dtype=np.uint8))

    cam = FileReplaySource(tmp_path, fps_target=120.0)
    cam.open()
    try:
        with caplog.at_level(logging.WARNING, logger="curbcam.camera.file_replay"):
            frames = []
            while (got := cam.read()) is not None:
                frames.append(got)
        # Both good frames were yielded; the corrupt one was skipped.
        assert len(frames) == 2
        # A warning was logged for the skipped file.
        assert any("Failed to decode replay frame" in r.message for r in caplog.records)
    finally:
        cam.close()
