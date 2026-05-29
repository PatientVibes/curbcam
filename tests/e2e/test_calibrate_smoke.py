import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.mark.e2e
def test_calibration_wizard_creates_active_calibration(live_server) -> None:  # type: ignore[no-untyped-def]
    base_url, sup = live_server
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # browser not installed in this environment
            pytest.skip("chromium not installed")
        ctx = browser.new_context()
        # Authenticate (shares cookies with the browser context).
        ctx.request.post(f"{base_url}/api/auth/login", form={"password": "pw"})
        page = ctx.new_page()
        page.goto(f"{base_url}/setup/calibrate")

        page.click("#capture")
        page.wait_for_function("document.getElementById('frame').naturalWidth > 0")

        canvas = page.locator("#cal-canvas")
        box = canvas.bounding_box()
        # Two points 100 display-px apart. With a 640-wide source shown at ~640,
        # scale ~= 1, so ~100 source px.
        page.mouse.click(box["x"] + 100, box["y"] + 100)
        page.mouse.click(box["x"] + 200, box["y"] + 100)

        page.fill("#distance", "5")
        page.select_option("#units", "m")
        page.select_option("#direction", "L2R")
        page.click("#submit")
        page.wait_for_selector("#result:has-text('Saved')")
        browser.close()

    active = sup.calibrations.get_active()
    assert active is not None
    # 5 m over ~100 px ≈ 50 mm/px; allow slack for canvas scaling/rounding.
    assert 30.0 <= float(active.mm_per_px_l2r) <= 90.0
