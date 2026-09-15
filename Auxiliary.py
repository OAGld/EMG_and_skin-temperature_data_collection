import os
from os import walk
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons

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


def plot_data_ext(self):

    # ---------------------------------------------------------
    # Read EMG data
    # ---------------------------------------------------------

    emg = pd.read_csv(
        self.emg_file,
        sep=r"\s+",
        header=None
    )

    emg_time = pd.to_datetime(
        emg.iloc[:, 0],
        unit="s"
    )

    # ---------------------------------------------------------
    # Read temperature data
    # ---------------------------------------------------------

    temperature = pd.read_csv(
        self.temperature_file,
        sep=r"\s+",
        header=None
    )

    temperature_time = pd.to_datetime(
        temperature.iloc[:, 0],
        unit="s"
    )

    # ---------------------------------------------------------
    # Read events
    # ---------------------------------------------------------

    events_from_file = []

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

    line, = ax_emg.plot(
        emg_time,
        emg.iloc[:, current_channel]
    )

    ax_emg.set_ylabel("EMG")
    ax_emg.set_title(
        f"EMG Channel {current_channel} with Events"
    )

    # ---------------------------------------------------------
    # Temperature plot
    # ---------------------------------------------------------

    temperature_line, = ax_temp.plot(
        temperature_time,
        temperature.iloc[:, 1]
    )

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