# Co-plan Review — MVP-1 Plan — Gemini 2.5 Pro

Second-opinion review of `2026-05-28-curbcam-mvp-1-headless-foundation.md` v1,
performed via the `co-plan` skill against `gemini-2.5-pro`. The plan was
piped in alongside `@docs/specs/2026-05-28-curbcam-design.md` (the spec it
implements), `@D:/speed-camera/source/speed-cam.py`, and
`@D:/speed-camera/source/config.py` for algorithm-parity reference.

Findings reproduced verbatim below. See the commit that follows this file
for which findings were accepted, partially accepted, or pushed back on,
and the corresponding plan edits.

---
Warning: 256-color support not detected. Using a terminal with at least 256-color support is recommended for a better visual experience.
Ripgrep is not available. Falling back to GrepTool.
Here is a review of the implementation plan for `curbcam` MVP-1.

### **CRITICAL**

1.  **Incorrect Frame Timestamps in Detector:** In **Task 4 (`find_motion`)**, the detection timestamp is generated using `time.monotonic()` at the *end* of the function. This is incorrect. The timestamp should correspond to the time the frame was captured. The `PipelineRunner` in **Task 14** receives a timestamp `_ts` from `camera.read()`, but this is never passed down to `find_motion`. This will lead to inaccurate speed calculations, as the `dt` in `speed_from_track` will be based on when the detection computation finished, not when the object was actually at that position.
    *   **Fix:** Modify `find_motion` to accept `frame_ts: float` as an argument and use it when creating `Detection` objects. The `PipelineRunner._process_frame` must be updated to pass the timestamp it receives from `camera.read()`.

2.  **Infinite Loop in Pipeline Runner:** The `PipelineRunner._loop_with_reconnect` in **Task 14** has a bug that causes an infinite loop for finite camera sources (like `FileReplaySource(loop=False)`). The `run_until_camera_exhausted` function will run, exhaust the camera, and return. The `_loop_with_reconnect` will then `sleep(0.5)` and call it again. Because `camera.close()` is called and `camera.open()` is called on the next iteration, the file source is reset and re-read from the beginning, causing an endless loop of processing the same file.
    *   **Fix:** `_loop_with_reconnect` is intended for persistent camera sources. For finite sources (indicated by `loop=False` on `FileReplaySource` or a new attribute on the `Camera` protocol), the loop should exit. The `detect --once` flag correctly handles this by not using `_loop_with_reconnect`, but any background execution of a finite source will loop forever. A simple fix is to have `run_until_camera_exhausted` return a status (e.g., `True` if exhausted) and have the reconnect loop break if that status is returned.

### **IMPORTANT**

1.  **Unicode Rendering Bug in `MediaWriter`:** In **Task 9 (`MediaWriter._annotate`)**, the code uses `cv2.putText` to draw direction arrows (`→`, `←`). OpenCV's default Hershey fonts do not support non-ASCII characters and will likely render a question mark or garbage. This is a significant cosmetic bug in the primary output artifact (the event image).
    *   **Fix:** Replace `cv2.putText` with text rendering via the `Pillow` (PIL) library, which correctly handles unicode characters when using a suitable font file (like DejaVu Sans). This involves converting the `numpy` array to a `Pillow` image, drawing text, and converting back.

2.  **Missing Integration Test for R2L Direction:** The integration test in **Task 14** (`test_runner_processes_synthetic_run_and_writes_an_event`) only validates a Left-to-Right (L2R) vehicle path. There is no corresponding integration test to ensure the entire pipeline correctly processes a Right-to-Left (R2L) track and applies the `mm_per_px_r2l` calibration factor.
    *   **Fix:** Add a new integration test case that uses a synthetic run with R2L motion and asserts that an event is created with the `R2L` direction and a speed calculated from the `mm_per_px_r2l` setting.

3.  **Missing Test for "No Active Calibration" Scenario:** The pipeline runner's `_persist_track` function in **Task 14** has a code path to handle cases where no active calibration is found in the database. The integration test in the same task always seeds a calibration beforehand. There is no test to verify that the runner behaves correctly (i.e., logs a message and skips persistence without crashing) when a track is finalized but no calibration is active.
    *   **Fix:** Add an integration test that runs the pipeline against a synthetic run *without* first seeding a calibration, and assert that no `Event` is created in the database.

### **NIT**

1.  **Missing Test for DB Unique Constraint:** The schema in **Task 7** correctly defines a unique partial index to ensure only one calibration can be active. However, there is no test that attempts to violate this constraint at the database level to confirm it works as a defense-in-depth measure. The repository test in **Task 8** only checks the repository's logic, not the underlying schema enforcement.
    *   **Suggestion:** Add a test that bypasses the `CalibrationRepo` and uses raw SQLAlchemy Core or a direct DB connection to try inserting two active calibrations, asserting that an `IntegrityError` is raised.

2.  **Potential Flakiness in Manual Smoke Test:** The manual test in **Task 15** uses `uv run python -c "..."` with a multi-line string. This can be fragile in some shells (especially PowerShell).
    *   **Suggestion:** For robustness, it would be better to write the small Python script to a temporary file (`.py`) and execute that file.

3.  **Pre-release Semver Tag:** **Task 19** uses `v0.1.0-mvp-1` as the tag. This is valid SemVer for a pre-release, but it's worth noting that some tooling might treat `v0.1.0` and `v0.1.0-mvp-1` differently. If the goal is to mark the first shippable (even if minimal) version, `v0.1.0` might be more appropriate. This is a process choice, not a technical error.

4.  **WAL Journaling Test Weakness:** The test `test_wal_journaling_is_enabled` in **Task 7** only checks the PRAGMA on the first connection. While the `journal_mode` is persistent for a SQLite database file, the test would be slightly more robust if it re-opened a connection to the same file to verify the setting was retained.

### **Areas of Good Coverage**

*   **Spec-to-Plan Coverage:** The plan does an excellent job of covering the headless requirements from the design spec (§13.1). All major features (per-direction calibration, history preservation, lazy-imports, indexing, WAL mode) are mapped to specific tasks.
*   **Ordering and Dependencies:** The task ordering is logical and follows a TDD-style progression. Potential import issues are correctly handled by creating files in the right order and expecting initial failures.
*   **Alembic Workflow:** The plan correctly uses `alembic revision --autogenerate` on a new/empty database to create the initial schema migration, which is the standard workflow.
*   **CLI Argument Passing:** Contrary to one of the review questions, the CLI test in **Task 15** correctly passes the `--data-dir` argument to both the `calibrate` and `detect` subcommands, ensuring they operate on the same database. The plan is correct here.

