# EMG and skin temperature data collection

A data-collection tool for a master's thesis. It streams biosignals from a [SiFi Labs](https://sifilabs.com/) BioArmband over Bluetooth Low Energy, logs them to CSV, and provides a control panel for recording, event marking, session notes, live visualization, signal-quality checks and screen-guided gesture training.

Recorded signals: EMG (8 channels), IMU, ECG, EDA, PPG and skin temperature. Each one can be switched on or off in `config.toml`.

## Requirements

- Python 3.11 or newer (the config is read with `tomllib`)
- A SiFi Labs BioArmband, powered on and in Bluetooth range
- A Bluetooth adapter on the computer
- `curl`, used to download the gesture images on start-up

The `sifibridge` program that talks to the armband is installed with the Python packages (`sifibridge-bin`), so it doesn't need to be downloaded separately.

## Installation

```bash
git clone https://github.com/OAGld/EMG_and_skin-temperature_data_collection.git
cd EMG_and_skin-temperature_data_collection
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

All run parameters live in `config.toml`:

| Section | Setting | What it does |
| --- | --- | --- |
| top level | `subject` | Name of the subject's data folder. Must end with `/`, e.g. `"subject1/"` |
| top level | `media_folder` | Where gesture images are stored. Must end with `/` |
| top level | `gestures` | IDs of the gestures to use, from [LibEMGGestures](https://github.com/libemg/LibEMGGestures) |
| `[sgt_args]` | `num_reps`, `rep_time`, `rest_time` | Repetitions per gesture, and the length of each repetition and rest in seconds |
| `[sgt_args]` | `auto_advance`, `discrete` | Advance automatically, or hold the space bar during each repetition |
| `[streamer]` | `name` | Bluetooth name of the armband, e.g. `"SifiBand_2F4C"` |
| `[streamer]` | `ecg`, `emg`, `eda`, `imu`, `ppg`, `temperature` | Turn each signal on or off |
| `[streamer]` | `*_fs`, `ppg_sps`, `ppg_avg` | Sampling rates. Only values the hardware supports are accepted |
| `[streamer]` | `filtering`, `emg_notch_freq`, `emg_bandpass`, `eda_bandpass` | On-device filtering |

Booleans must be lowercase (`true` / `false`).

A copy of `config.toml` is saved to the subject's data folder on every run, so each recording keeps the settings it was made with.

## Running

```bash
source .venv/bin/activate
python main.py
```

On start-up the program downloads the selected gesture images, connects to the armband and opens the main window. The status indicators at the top show whether the armband is streaming and whether a recording is running. The program reconnects automatically if the Bluetooth link drops.

### Main window

| Panel | Contents |
| --- | --- |
| Session info | Age, gender, date, time, outside temperature and comments. Saved as a `.txt` file in the data folder |
| Controls | Start / Stop recording, Visualize, Monitor data, Screen guided gesturing, Plot data, Reset data, Set baseline, Analyze device, Exit |
| Events | One button per gesture, plus fixed events (Stop gesture, Enter/Exit sauna, Enter/Exit fridge, Move location) and a custom event |
| Console output | Everything the program prints, including warnings from the streamer |

Closing the window with the X button asks for confirmation first.

### Signal-quality monitor

**Monitor data** opens a live window that checks the EMG while you record:

- **Baseline:** compares the moving MAV (mean absolute value) with the resting level. It's only active after **Set baseline** has been run, which records 5 seconds with the subject at rest.
- **Amplitude:** flags channels whose peak goes above the expected sEMG range (5 mV).
- **Packets:** compares the number of EMG samples received with the configured sampling rate, to detect dropped Bluetooth packets.

Out-of-range amplitudes and dropped packets are also written as events. Buttons under the plots reset the EMG and MAV y-axes.

### Screen-guided gesturing

**Screen guided gesturing** clears the data buffer and opens a separate window that prompts the subject through each gesture. It doesn't record data itself. It writes the start and stop of each repetition as events, so start a recording as well.

## Output

Each subject gets a folder under `data/<subject>/`:

| File | Contents |
| --- | --- |
| `emg.csv`, `imu.csv`, `ecg.csv`, `eda.csv`, `ppg.csv`, `temperature.csv` | One file per enabled signal. Space-separated; column 0 is the host timestamp (Unix time) and the rest are channels |
| `events.json` | One JSON object per line: `{"timestamp": <unix time>, "event": "<name>"}` |
| `config.toml` | The configuration used for the session |
| `<name>.txt` | Session info and comments, if saved from the Session info panel |

Samples are written in batches, and each batch gets one timestamp, so many rows share the same timestamp. **Plot data** shows the recorded EMG and temperature with the events marked.

## Project structure

```
main.py                     Entry point: reads config.toml, starts the streamer and the main window
menu.py                     Main Tkinter window
Auxiliary.py                Signal-quality monitor and baseline, plotting, gesture download
config.toml                 Run configuration
CustomLibEMG/               Modified copies of libemg components
├── streamers.py            Sets up shared memory and starts the armband streamer
├── Streamer/               Armband streamer (sifibridge, reconnects, packet-loss tracking)
├── OnlineDataHandler.py    Reads shared memory, logs to CSV, live visualization
├── gui.py                  Window for screen-guided gesturing
└── SGT/                    Screen-guided gesturing panel
```

The streamer, the CSV logger, the visualizer and the gesture window each run in their own process. They share data through named shared memory.

## Known limitations

- **EMG above 1000 Hz loses samples:** the Bluetooth link can't keep up, losing about 35% at 1600 Hz and about 40% at 2000 Hz. The packet check in **Monitor data** shows the rate actually received.
- **IMU at 200 Hz:** setting it to 200 Hz stops the IMU sending data until the armband is power-cycled.

## Acknowledgements

Built on [LibEMG](https://github.com/libemg/libemg) and [sifi-bridge-py](https://pypi.org/project/sifi-bridge-py/). Gesture images are from [LibEMGGestures](https://github.com/libemg/LibEMGGestures).
