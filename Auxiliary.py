import os
from os import walk
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons
from matplotlib.animation import FuncAnimation
from multiprocessing import Process
import matplotlib.pyplot as plt
from matplotlib import pyplot
import numpy as np
import time
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class data_QA_continuous():

    def __init__(self, odh, event_callback=None):
        self.odh = odh
        self.event_callback = event_callback    # called with an event name, e.g. Menu.create_event
        self.baseline_mav = None    # mean of windowed MAV, all channels combined
        self.baseline_std = None    # std of windowed MAV, all channels combined
        self.baseline_window_size = None

    def set_baseline(self):
        """Calibrate the resting EMG level used by the data quality check.

        Clears the buffer, records 5 seconds of EMG while the subject is at rest,
        and splits it into 25 windows. The mean absolute value (MAV) of each window,
        averaged over all channels, gives the baseline mean and standard deviation.
        monitor_data compares the live MAV against baseline + 3 std to tell whether
        a muscle contraction is visible in the signal.
        """
        self.odh.reset()
        print(f"Wait 5 seconds.")

        for i in range(1, 6):
            print(i)
            time.sleep(1)

        data, count = self.odh.get_data(N=0, filter=False)
        emg = np.asarray(data['emg'])      # assumed shape: (samples, channels)

        # Keep only valid samples (drop unfilled zero rows)
        n_valid = int(np.asarray(count['emg']).item())
        emg = emg[:n_valid]

        # Remove DC offset (per channel)
        emg = emg - emg.mean(axis=0)

        # Split into non-overlapping windows
        n_windows = 25
        window_size = emg.shape[0] // n_windows
        if window_size < 1:
            raise ValueError("Not enough baseline data to compute a standard deviation.")
        windows = emg[:n_windows * window_size].reshape(n_windows, window_size, -1)

        # One MAV per window, averaged over samples AND channels -> shape (n_windows,)
        mav = np.mean(np.abs(windows), axis=(1, 2))

        self.baseline_mav = mav.mean()
        self.baseline_std = mav.std(ddof=1)
        self.baseline_window_size = window_size

        print("calibration complete")

    def monitor_data(self, parent=None, num_samples=1000, interval_ms=500, max_points=5000, amp_limit=5e-3,
                     emg_fs=None, loss_window_s=5, loss_limit=0.01):
        """Open a live window for checking EMG signal quality during recording.

        Shows three panels, refreshed every interval_ms:
        - The most recent num_samples of raw EMG, one stacked trace per channel
          with the DC offset removed.
        - The moving-window MAV across all channels, using the same window
          length as set_baseline so the values are comparable.
        - Three status indicators:
          - Baseline: green when the MAV is at rest level, red when it is above
            baseline + 3 std. Only active once set_baseline has been run.
          - Amplitude: red when the peak amplitude (DC offset removed) of any
            channel exceeds amp_limit, i.e. the signal is outside the expected
            sEMG range of 10 mV peak-to-peak. The affected channels are named
            in the indicator and printed to the console when the check fails.
          - Packets: compares how many EMG samples arrived over the last
            loss_window_s seconds (growth of emg_count) with emg_fs. Red when
            more than loss_limit of the expected samples are missing. The
            streamer drops lost samples, so this catches dropped packets
            without changing how data is stored. Skipped if emg_fs is None.
            Each time it starts dropping, a "Dropped packets" event is passed to
            event_callback (if set), so the dropout shows up in events.json.
        The EMG and MAV y-axes auto-scale to the largest value seen since the
        window opened, or since their "Reset ... y-axis" button was last pressed.
        """

        # ==================== Shared setup ====================
        # Window, figure, raw EMG panel and indicator panel used by all three checks

        win = tk.Toplevel(parent)
        win.title("EMG Monitor")

        sample, _ = self.odh.get_data(N=1, filter=False)
        n_ch = sample['emg'].shape[1]

        fig = Figure(figsize=(9, 7), tight_layout=True)
        gs = fig.add_gridspec(3, 1, height_ratios=[4, 3, 2])

        # Raw EMG panel: one stacked trace per channel
        ax_stack = fig.add_subplot(gs[0])
        ax_stack.set_title("EMG data all channels")
        ax_stack.set_xlim(0, num_samples)
        ax_stack.set_yticks([])
        lines_stack = [ax_stack.plot([], [], lw=0.8)[0] for _ in range(n_ch)]

        # Indicator panel: no ticks or frame, just text and colored boxes
        ax_ind = fig.add_subplot(gs[2])
        ax_ind.set_xlim(0, 1)
        ax_ind.set_ylim(0, 1)
        ax_ind.axis("off")

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill="both", expand=True)

        # Button bar under the plots; packed before the canvas so it stays visible when the window is shrunk
        buttons = tk.Frame(win)
        buttons.pack(side="bottom", pady=4, before=canvas.get_tk_widget())

        stride = max(1, num_samples // max_points)
        state = {"job": None, "peak": 1e-9}
        
        # ==================== Baseline check (MAV above baseline + 3 std) ====================

        ax_mav = fig.add_subplot(gs[1], sharex=ax_stack)
        ax_mav.set_title("MAV (all channels)")
        ax_mav.set_xlabel("Samples")
        line_mav, = ax_mav.plot([], [], lw=1.2, color="tab:blue", label="MAV")
        # Baseline reference lines (hidden until set_baseline has been run)
        base_line = ax_mav.axhline(0, color="green", ls="-", lw=1, visible=False, label="baseline")
        thr_line = ax_mav.axhline(0, color="red", ls="--", lw=1, visible=False, label="baseline + 3σ")
        ax_mav.legend(loc="upper left", fontsize=8)

        status = ax_ind.text(0.02, 0.83, "NO BASELINE", ha="left", va="center",
                     fontsize=12, fontweight="bold", color="white",
                     bbox=dict(boxstyle="round,pad=0.5", fc="grey", ec="none"))
        detail = ax_ind.text(0.30, 0.83, "", ha="left", va="center", fontsize=10)

        state["mav_top"] = 1e-9

        # Forget the largest MAV and EMG amplitude seen so far; the next tick rescales to the current data
        def reset_ylim():
            state["mav_top"] = 1e-9
            state["peak"] = 1e-9

        tk.Button(buttons, text="Reset y-axes", command=reset_ylim).pack(side="left", padx=4)

        # ==================== Amplitude check (outside expected sEMG range) ====================

        amp_status = ax_ind.text(0.02, 0.5, "AMPLITUDE OK", ha="left", va="center",
                     fontsize=12, fontweight="bold", color="white",
                     bbox=dict(boxstyle="round,pad=0.5", fc="grey", ec="none"))
        amp_detail = ax_ind.text(0.30, 0.5, "", ha="left", va="center", fontsize=10)

        state["amp_bad"] = []

        # ==================== Packet check (dropped samples) ====================

        loss_status = ax_ind.text(0.02, 0.17, "NO RATE SET" if emg_fs is None else "MEASURING...",
                     ha="left", va="center", fontsize=12, fontweight="bold", color="white",
                     bbox=dict(boxstyle="round,pad=0.5", fc="grey", ec="none"))
        loss_detail = ax_ind.text(0.30, 0.17, "", ha="left", va="center", fontsize=10)

        state["count_hist"] = []
        state["dropping"] = False

        def tick():
            try:
                # ---------- Shared: fetch data ----------
                data, count = self.odh.get_data(N=num_samples, filter=False)
                rows = data['emg']
                emg_count = int(np.asarray(count['emg']).item())
                n = min(num_samples, emg_count, rows.shape[0])

                # Same window length as the baseline, so values are comparable
                w = self.baseline_window_size or max(1, num_samples // 25)

                if n >= max(2, w):
                    # ---------- Shared: preprocess and plot raw EMG ----------
                    y = rows[:n][::-1].astype(float)      # newest-first -> left to right
                    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
                    y = y - y.mean(axis=0)                # remove DC offset per channel
                    state["peak"] = max(state["peak"], np.abs(y).max())
                    step = 2 * state["peak"]
                    x = np.arange(num_samples - n, num_samples)[::stride]

                    ys = y[::stride]
                    for j in range(n_ch):
                        lines_stack[j].set_data(x, ys[:, j] + j * step)
                    ax_stack.set_ylim(-step, n_ch * step)

                    # ---------- Baseline check ----------
                    # MAV over samples AND channels, moving window of length w
                    inst = np.abs(y).mean(axis=1)
                    mav = np.convolve(inst, np.ones(w) / w, mode="valid")
                    x_mav = np.arange(num_samples - n + w - 1, num_samples)
                    line_mav.set_data(x_mav[::stride], mav[::stride])

                    top = max(state["mav_top"], mav.max())
                    if self.baseline_mav is not None:
                        thr = self.baseline_mav + 3 * self.baseline_std
                        base_line.set_ydata([self.baseline_mav] * 2)
                        thr_line.set_ydata([thr] * 2)
                        base_line.set_visible(True)
                        thr_line.set_visible(True)
                        top = max(top, thr)

                        above = mav[-1] > thr
                        status.set_text("ABOVE BASELINE" if above else "AT BASELINE")
                        status.get_bbox_patch().set_facecolor("tab:red" if above else "tab:green")
                        detail.set_text(f"MAV {mav[-1]:.3g}   |   threshold {thr:.3g}")
                    state["mav_top"] = top
                    ax_mav.set_ylim(0, 1.2 * top)

                    # ---------- Amplitude check ----------
                    # Peak amplitude per channel against the sEMG limit
                    ch_peak = np.abs(y).max(axis=0)
                    bad = [j + 1 for j in range(n_ch) if ch_peak[j] > amp_limit]
                    if bad:
                        amp_status.set_text("OUT OF RANGE")
                        amp_status.get_bbox_patch().set_facecolor("tab:red")
                        amp_detail.set_text(f"ch {', '.join(map(str, bad))}   |   "
                                            f"max peak {ch_peak.max() * 1e3:.2f} mV > {amp_limit * 1e3:.2f} mV")
                    else:
                        amp_status.set_text("AMPLITUDE OK")
                        amp_status.get_bbox_patch().set_facecolor("tab:green")
                        amp_detail.set_text(f"max peak {ch_peak.max() * 1e3:.2f} mV")
                    # Print only when the set of out-of-range channels changes, to avoid spamming the console
                    if bad and bad != state["amp_bad"]:
                        peaks = ", ".join(f"ch {c}: {ch_peak[c - 1] * 1e3:.2f} mV" for c in bad)
                        print(f"Amplitude above {amp_limit * 1e3:.2f} mV on {peaks}")
                    state["amp_bad"] = bad

                # ---------- Packet check ----------
                # Received samples (growth of emg_count) vs emg_fs
                if emg_fs is not None:
                    now = time.time()
                    hist = state["count_hist"]
                    if hist and emg_count < hist[-1][1]:
                        hist.clear()                      # buffer was reset, start over
                    hist.append((now, emg_count))
                    # Keep the newest entry that is at least loss_window_s old as the reference
                    while len(hist) > 1 and hist[1][0] <= now - loss_window_s:
                        hist.pop(0)
                    dt = now - hist[0][0]
                    if dt >= loss_window_s:
                        received = emg_count - hist[0][1]
                        expected = emg_fs * dt
                        missing = max(0.0, (expected - received) / expected)
                        dropping = missing > loss_limit
                        loss_status.set_text("DROPPING SAMPLES" if dropping else "PACKETS OK")
                        loss_status.get_bbox_patch().set_facecolor("tab:red" if dropping else "tab:green")
                        loss_detail.set_text(f"rate {received / dt:.0f} / {emg_fs:g} Hz   |   "
                                             f"missing {100 * missing:.1f}% (last {dt:.0f} s)")
                        # Print and log an event only when it starts dropping, to avoid spamming
                        if dropping and not state["dropping"]:
                            print(f"Dropping EMG samples: {received / dt:.0f} of {emg_fs:g} Hz received "
                                  f"({100 * missing:.1f}% missing over the last {dt:.0f} s)")
                            if self.event_callback is not None:
                                self.event_callback("Dropped packets")
                        state["dropping"] = dropping
                    else:
                        loss_status.set_text("MEASURING...")
                        loss_status.get_bbox_patch().set_facecolor("grey")
                        loss_detail.set_text("")

                # ---------- Shared: redraw ----------
                canvas.draw_idle()
            except Exception as e:
                print("monitor_data tick error:", e)
            state["job"] = win.after(interval_ms, tick)

        def on_close():
            if state["job"] is not None:
                win.after_cancel(state["job"])
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)
        tick()
        return win


def download_gestures(gesture_ids, folder, download_imgs=True, download_gifs=False, redownload=False):
    """
    Downloads gesture images (either .png or .gif) from: 
    https://github.com/libemg/LibEMGGestures.
    
    This function dowloads gestures using the "curl" command. 

    Parameters
    ----------
    gesture_ids: list
        A list of indexes corresponding to the gestures you want to download. A list of indexes and their respective 
        gesture can be found at https://github.com/libemg/LibEMGGestures.
    folder: string
        The output folder where the downloaded gestures will be saved.
    download_gif: bool (optional), default=False
        If True, the assocaited GIF will be downloaded.
    redownload: bool (optional), default=False
        If True, all files will be re-downloaded (regardless if they are already downloaed).
    """
    git_url = "https://raw.githubusercontent.com/libemg/LibEMGGestures/main/"
    gif_folder = "GIFs/"
    img_folder = "Images/"
    json_file = "gesture_list.json"
    curl_commands = "curl --create-dirs" + " -O --output-dir " + folder + " "

    files = next(walk(folder), (None, None, []))[2]

    # Check JSON file exists
    if not json_file in files or redownload:
        os.system(curl_commands + git_url + json_file)

    json_file = json.load(open(folder + json_file))

    for id in gesture_ids:
        idx = str(id)
        img_file = json_file[idx] + ".png"
        gif_file = json_file[idx] + ".gif"
        if download_imgs and (not img_file in files or redownload):
            os.system(curl_commands + git_url + img_folder + img_file)
        if download_gifs:
            if not gif_file in files or redownload:
                os.system(curl_commands + git_url + gif_folder + gif_file)


def _read_data_file(file_path):
    """Read a space-separated data file, or return None if it is missing or empty."""

    try:
        data = pd.read_csv(
            file_path,
            sep=r"\s+",
            header=None
        )
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return None

    if data.empty:
        return None

    return data


def plot_data_ext(self):

    # ---------------------------------------------------------
    # Read EMG data
    # ---------------------------------------------------------

    emg = _read_data_file(self.emg_file)

    if emg is not None:
        emg_time = pd.to_datetime(
            emg.iloc[:, 0],
            unit="s"
        )

    # ---------------------------------------------------------
    # Read temperature data
    # ---------------------------------------------------------

    temperature = _read_data_file(self.temperature_file)

    if temperature is not None:
        temperature_time = pd.to_datetime(
            temperature.iloc[:, 0],
            unit="s"
        )

    if emg is None and temperature is None:
        print("No data to plot. Record some data first.")
        return

    # ---------------------------------------------------------
    # Read events
    # ---------------------------------------------------------

    events_from_file = []

    if os.path.exists(self.events_file):

        with open(self.events_file, "r") as f:

            for line in f:

                line = line.strip()

                if line:
                    events_from_file.append(json.loads(line))

    # ---------------------------------------------------------
    # Create figure with two plots
    # ---------------------------------------------------------

    fig, (ax_emg, ax_temp) = plt.subplots(
        2,
        1,
        sharex=True,
        figsize=(12, 8)
    )

    # Make room for channel selector
    plt.subplots_adjust(
        left=0.1,
        right=0.8,
        hspace=0.15
    )

    # ---------------------------------------------------------
    # EMG plot
    # ---------------------------------------------------------

    current_channel = 1

    if emg is not None:
        line, = ax_emg.plot(
            emg_time,
            emg.iloc[:, current_channel]
        )
        ax_emg.set_title(
            f"EMG Channel {current_channel} with Events"
        )
    else:
        ax_emg.text(0.5, 0.5, "No EMG data", ha="center", va="center", transform=ax_emg.transAxes)
        ax_emg.set_title("EMG")

    ax_emg.set_ylabel("EMG")

    # ---------------------------------------------------------
    # Temperature plot
    # ---------------------------------------------------------

    if temperature is not None:
        temperature_line, = ax_temp.plot(
            temperature_time,
            temperature.iloc[:, 1]
        )
    else:
        ax_temp.text(0.5, 0.5, "No temperature data", ha="center", va="center", transform=ax_temp.transAxes)

    ax_temp.set_xlabel("Time")
    ax_temp.set_ylabel("Temperature")
    ax_temp.set_title("Skin Temperature")

    # ---------------------------------------------------------
    # Events on both plots
    # ---------------------------------------------------------

    for event in events_from_file:

        event_time = pd.to_datetime(
            event["timestamp"],
            unit="s"
        )

        # EMG
        ax_emg.axvline(
            event_time,
            linestyle="--"
        )

        ax_emg.text(
            event_time,
            ax_emg.get_ylim()[1],
            event["event"],
            rotation=90,
            verticalalignment="top"
        )

        # Temperature
        ax_temp.axvline(
            event_time,
            linestyle="--"
        )

    # ---------------------------------------------------------
    # Channel selector
    # ---------------------------------------------------------

    if emg is None:
        fig.autofmt_xdate()
        plt.show()
        return

    selector_ax = plt.axes(
        [0.82, 0.25, 0.15, 0.5]
    )

    channels = [
        "Channel 1",
        "Channel 2",
        "Channel 3",
        "Channel 4",
        "Channel 5",
        "Channel 6",
        "Channel 7",
        "Channel 8"
    ]

    radio = RadioButtons(
        selector_ax,
        channels
    )

    # ---------------------------------------------------------
    # Change EMG channel
    # ---------------------------------------------------------

    def change_channel(label):

        channel = int(label.split()[-1])

        line.set_ydata(
            emg.iloc[:, channel]
        )

        ax_emg.set_title(
            f"EMG Channel {channel} with Events"
        )

        ax_emg.relim()
        ax_emg.autoscale_view()

        fig.canvas.draw_idle()

    radio.on_clicked(change_channel)

    # ---------------------------------------------------------
    # Formatting
    # ---------------------------------------------------------

    fig.autofmt_xdate()

    plt.show()