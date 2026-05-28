from pathlib import Path

import cv2
import numpy as np

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
