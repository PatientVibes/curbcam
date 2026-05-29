import pytest

from curbcam.web.streams import mjpeg_generator


class _FakeSup:
    def __init__(self) -> None:
        self.viewers = 0

    def add_viewer(self) -> None:
        self.viewers += 1

    def remove_viewer(self) -> None:
        self.viewers -= 1

    def latest_annotated(self) -> bytes | None:
        return b"\xff\xd8JPEGDATA"


@pytest.mark.asyncio
async def test_mjpeg_generator_yields_multipart_jpeg_and_refcounts() -> None:
    sup = _FakeSup()
    gen = mjpeg_generator(sup, fps=1000.0)
    chunk = await gen.__anext__()
    assert b"--frame" in chunk
    assert b"image/jpeg" in chunk
    assert b"\xff\xd8" in chunk
    assert sup.viewers == 1
    await gen.aclose()
    assert sup.viewers == 0
