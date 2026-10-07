# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

EMG data-collection tool for a master's thesis. It streams biosignals (EMG, IMU, ECG, EDA, PPG, temperature) from a SiFi Labs BioArmband over BLE, logs them to CSV, and provides a Tkinter control panel for recording, event marking, session notes, live visualization, signal-quality checks, and screen-guided gesture training (SGT).

## Running

```bash
source .venv/bin/activate
pip install -r requirements.txt   # Python 3.11+ (uses tomllib)
python main.py
```

There are no tests, linter, or build step. Running requires the physical armband (`[streamer].name` in `config.toml`) to be powered and in range. `gestures/` is populated automatically on start by curling images from the LibEMGGestures GitHub repo.

All run parameters live in `config.toml` (subject, gesture IDs, SGT reps/timing, sensor enables, sampling rates, filtering). `main.py` copies it into the subject's data folder on every run so each recording keeps the config it used.

## Architecture

The program is multi-process, and the processes communicate through **named shared memory**, not by passing objects:

1. **Streamer process**: `CustomLibEMG/streamers.py::sifi_bioarmband_streamer` defines one shared-memory buffer per enabled modality (e.g. `emg` `(3000,8)`, plus an `emg_count` counter). It then starts `SiFiBridgeStreamer` (`CustomLibEMG/Streamer/_sifi_bridge_streamer.py`, a `multiprocessing.Process`), which drives the `sifibridge` subprocess via `sifi-bridge-py`. That process writes newest-first rolling buffers and handles reconnects and packet-loss tracking. It validates sampling rates against hardware-supported values.
2. **OnlineDataHandler** (`CustomLibEMG/OnlineDataHandler.py`): this is a modified copy of libemg's ODH. It attaches to the shared memory by tag. `log_to_file` spawns a separate process that appends new samples to `<data_folder><modality>.csv` (space-separated, column 0 = host timestamp stamped per *batch*, so many rows share a timestamp). `visualize` and `analyze_hardware` also live here. Child processes are stopped by setting `log_signal`/`visualize_signal` Events (`stop_all`).
3. **Menu** (`menu.py`): this is the Tkinter main window and runs on the main thread. It redirects `sys.stdout`/`stderr` into an in-window console through a queue that is polled with `after()`, so `print()` from threads is safe. It checks `odh._check_streaming()` every second.
4. **Data QA** (`Auxiliary.py::data_QA_continuous`): wraps the ODH. `set_baseline` is the QA calibration (windowed MAV mean/std at rest). `monitor_data` opens the live quality window (baseline, amplitude and dropped-packet checks). The Menu creates one instance as `self.qa`, before `create_gui()`, because `create_gui()` blocks in the Tk mainloop.
5. **SGT**: `Menu.start_sgt` launches `CustomLibEMG/gui.py::GUI` (DearPyGui) in its own process, which runs `SGT/_data_collection_panel.py`. SGT **does not record data**. It only appends gesture start/stop events (with rep number) to the shared `events.json`. `_data_collection_panel_odh_enabled.py` is an alternative variant that is currently unused.

Events (`events.json`) are JSON Lines (`{"timestamp": unix_time, "event": name}`), and both the Menu and SGT processes append to the file. Data is aligned to events by timestamp during plotting (`Auxiliary.plot_data_ext`, which plots samples at their batch timestamps and drops skin-temperature readings of 0).

`CustomLibEMG/` holds forked and patched copies of `libemg` components. Some modules still import upstream `libemg` (e.g. `SharedMemoryManager`, `FeatureExtractor` in the ODH, and the `libemg` streamers/ODH in `gui.py`). Check which one a change should target.

## Code structure

When a function does several things, structure it as an upside-down "tree" where possible:
- Put the variables, objects and code used by several functionalities in a **shared** group first.
- After that, give each functionality its own group with the variables, objects and code that only it uses.
- Mark each group with a banner comment, for example `# ==================== Shared setup ====================` or `# ==================== Amplitude check (outside expected sEMG range) ====================`. Use smaller `# ---------- ... ----------` sub-headers for the same grouping inside nested functions or loops.
- Each group adds the state keys it owns (e.g. `state["amp_bad"] = []`) instead of defining every key in one dict up front.

`data_QA_continuous.monitor_data` (in `Auxiliary.py`) is the reference example. It has a shared setup group, then one group each for the baseline check, the amplitude check and the packet check, and `tick()` follows the same grouping.

## Gotchas

- Paths are built by string concatenation, not `os.path.join`. `subject` in `config.toml` must end with `/` (e.g. `"subject1/"`), and `media_folder` must end with `/` too.
- The BioArmband BLE link loses samples above 1000 Hz EMG (~35% at 1600 Hz, ~40% at 2000 Hz). IMU at 200 Hz silences the IMU until a power cycle. Both are documented as constants in `_sifi_bridge_streamer.py`.
- Shared-memory buffer shapes in `streamers.py` must match what the streamer writes (e.g. EMG is 8 channels).
- `main.py` contains a to-do list at the top that tracks planned features.
- Git ignores `data/`, `gestures/`, `sifibridge` (binary), `Old_functions.py`, and `filter_testing.py`. These are scratch or local-only files.
