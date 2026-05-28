# Co-plan Review — 2026-05-28 — Gemini 2.5 Pro

Second-opinion design review of 2026-05-28-curbcam-design.md v1,
performed via the `co-plan` skill against `gemini-2.5-pro`. The spec was
piped in alongside `@D:/speed-camera/source/config.py` and
`@D:/speed-camera/source/speed-cam.py` as upstream reference, with sharp
prompts on missed dependencies, ordering, constraint violations, risks,
and verification sufficiency.

Findings are reproduced verbatim below. See the commit that follows this
file for which findings were accepted, partially accepted, or pushed back
on, and the corresponding spec edits.

---
Warning: 256-color support not detected. Using a terminal with at least 256-color support is recommended for a better visual experience.
Ripgrep is not available. Falling back to GrepTool.
Here is a review of the `curbcam` design specification, with findings categorized by severity.

### CRITICAL

1.  **Missed Concern: Privacy, Data Protection, and Legal Liability.** The specification does not address the legal and ethical implications of recording in a public or semi-public space. Depending on the jurisdiction, there can be strict laws (e.g., GDPR) regarding the capture of personally identifiable information, which includes faces and license plates. The upstream `pageauc/speed-camera` project operates in a gray area, and a from-scratch rewrite is an opportunity to address this head-on.
    -   **Risk:** Users could deploy `curbcam` in a way that violates local laws, creating legal liability for themselves and reputational risk for the project. Capturing license plates, even without OCR (§13.2), could be perceived as a form of surveillance.
    -   **Recommendation:** Add a new section to the spec addressing responsible use. This should include a prominent disclaimer about checking local laws, suggestions for anonymizing data (e.g., lower resolution, motion blur on non-vehicle areas), and a clear statement on the project's stance on privacy. This is a documentation/design issue, not just a technical one.

### IMPORTANT

1.  **Missed Feature: User-Extensible Hooks.** The upstream `speed-cam.py` supports a `user_motion_code.py` file (lines 400-413), allowing users to inject custom Python code that runs after a detection is complete. This is a powerful feature for the hobbyist/power-user audience, enabling custom integrations (e.g., turning on a light, sending a custom alert) without waiting for official project support. The spec defers alerts to v0.2+ (§13.2) but omits this local code execution hook entirely. While webhooks are a more modern approach, they don't offer the same flexibility as direct code execution for local hardware integrations.
    -   **Recommendation:** Acknowledge the power of user hooks. Consider adding a simple, well-defined plugin or webhook system to the MVP scope that can call a local shell script or Python function with event data. This would bridge the gap for power users coming from the upstream project.

2.  **Unaddressed Risk: Plaintext Secrets in Configuration.** The upstream `config.py` (line 64) and the new spec's proposed camera factory (§6) both use full RTSP URLs like `"rtsp://user:password@IP:..."`. This encourages storing plaintext credentials in the `curbcam.yaml` file. While common in hobbyist projects, this is a significant security risk.
    -   **Recommendation:** The spec should acknowledge this risk in §14 ("Risks"). Furthermore, §9 ("Configuration Model") should be updated to recommend using environment variables for sensitive fields, a feature that Pydantic-settings supports out of the box (e.g., `CURBCAM_CAMERA_SOURCE="rtsp://..."`). The `docker-compose.yml` (§11.1) could then demonstrate using an `.env` file, which is a standard, more secure pattern.

3.  **Unaddressed Risk: MJPEG Stream Token Leakage.** The spec proposes using a `?token=...` query parameter for embedding the MJPEG stream in external dashboards like Home Assistant (§10). If a user clicks a link on a page that embeds the stream, the security token can leak to the third-party site via the `Referer` HTTP header.
    -   **Recommendation:** The spec should require the MJPEG endpoint (`/api/stream.mjpeg`) to send a `Referrer-Policy: strict-origin-when-cross-origin` header to mitigate this risk. This is a simple but effective protection.

4.  **Verification Gap: No UI/Browser-Level Testing.** The spec explicitly defers browser tests (§12) for the MVP. However, the project's primary "killer feature" and main user interaction surface is the web UI, particularly the calibration wizard (§8.3). The spec itself calls out a critical bug to avoid in this wizard (the coordinate-transform problem). Without any automated browser tests, there is no safety net to prevent regressions in this most critical, interactive part of the application. Manual smoke testing is insufficient for ensuring long-term quality.
    -   **Recommendation:** Reconsider the "no browser tests" stance for the MVP. At a minimum, a single end-to-end test using Playwright or a similar tool that completes the first-run setup and calibration wizard would provide immense value and catch a whole class of otherwise untestable bugs.

5.  **Missed Feature: Day/Night Detection.** The upstream `config.py` has `IM_SAVE_4AI_DAY_THRESH` (line 104) and `speed-cam.py` uses an `is_daytime()` function (line 666) to avoid saving low-quality (dark) images for potential AI training. The `curbcam` spec defers AI/ML features but completely omits the concept of determining image quality based on ambient light. This is a loss of a useful feature that improves data quality for any future use, including manual review.
    -   **Recommendation:** Add a simple day/night threshold to the `DetectorSettings` (§9). The `pipeline/runner.py` can then use this to decide whether to store an event's images, perhaps storing the event metadata but flagging that the image was discarded due to low light.

### NIT (Nitpicks)

1.  **Missing Diagnostic: Detector FPS.** The upstream `config.py` has `LOG_FPS_ON` (line 51) and `speed-cam.py` uses `get_fps()` (line 654) to log the performance of the core detection loop. This is a valuable diagnostic for performance tuning. The `curbcam` spec does not mention exposing this metric. While the MJPEG stream is throttled, knowing the detector's actual processing speed is important.
    -   **Recommendation:** The `pipeline/runner.py` should calculate its processing FPS and expose it, perhaps via a debug endpoint or structured logs.

2.  **Ambiguous Spec: Image Annotation on Saved Files.** The spec mentions annotating the live MJPEG stream (§8.4, §8.5), but it's not explicit about what annotations (speed, bounding boxes, etc.) are drawn on the final JPEG files saved to disk (§7.2). The upstream project has extensive options for this (`IM_SHOW_TEXT_ON`, `IM_SHOW_CROP_AREA_ON`, etc in `config.py`).
    -   **Recommendation:** Clarify in §7.2 or a new section what, if any, annotations will be burned into the saved event images.

3.  **Implementation Detail: SQLite WAL Mode.** The spec correctly identifies that a single process with a writer thread and a reader (web) thread will be used. This model relies heavily on SQLite's Write-Ahead Logging (WAL) mode to prevent the writer (detector) from blocking readers (web server). While this is the default for Python's `sqlite3` in recent versions, it's critical enough to be stated explicitly.
    -   **Recommendation:** Add a note in §7.1 stating that the database connection must be configured to use WAL journaling mode.

4.  **Implementation Detail: Time Zone Display.** The spec makes the correct choice to store timestamps in UTC (`ts_utc` in §7.1). It also shows setting a `TZ` environment variable in Docker (§11.1). However, it doesn't specify *how* timestamps will be presented to the user in the UI. Consistently applying the `TZ` setting or, better yet, using the browser's local time zone for display, is a non-trivial detail worth a brief mention.
    -   **Recommendation:** Add a sentence to §8.2 ("Pages") clarifying that all timestamps shown in the UI will be localized (e.g., "All event times are displayed in the server's configured time zone.").

