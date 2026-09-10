import os
from os import walk
import json
import pandas as pd

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

    import matplotlib.pyplot as plt
    from matplotlib.widgets import RadioButtons

    emg = pd.read_csv(
        self.emg_file,
        sep=" ",
        header=None
    )

    emg_time = pd.to_datetime(
        emg.iloc[:, 0],
        unit="s"
    )

    # Read events
    events_from_file = []

    with open(self.events_file, "r") as f:
        for line in f:
            line = line.strip()

            if line:
                events_from_file.append(json.loads(line))

    # Create figure and axes
    fig, ax = plt.subplots()

    # Make room for channel selector
    plt.subplots_adjust(left=0.15, right=0.8)

    # Start with channel 1
    current_channel = 1

    line, = ax.plot(
        emg_time,
        emg.iloc[:, current_channel]
    )

    # Events
    for event in events_from_file:

        event_time = pd.to_datetime(
            event["timestamp"],
            unit="s"
        )

        ax.axvline(
            event_time,
            linestyle="--"
        )

        ax.text(
            event_time,
            ax.get_ylim()[1],
            event["event"],
            rotation=90,
            verticalalignment="top"
        )

    ax.set_xlabel("Time")
    ax.set_ylabel("EMG")
    ax.set_title(f"EMG Channel {current_channel} with Events")

    # Channel selector
    selector_ax = plt.axes([0.82, 0.25, 0.15, 0.5])

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

    # Function called when channel is selected
    def change_channel(label):

        channel = int(label.split()[-1])

        line.set_ydata(
            emg.iloc[:, channel]
        )

        ax.set_title(
            f"EMG Channel {channel} with Events"
        )

        ax.relim()
        ax.autoscale_view()

        fig.canvas.draw_idle()

    radio.on_clicked(change_channel)

    fig.autofmt_xdate()

    plt.show()