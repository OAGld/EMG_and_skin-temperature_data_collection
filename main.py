from menu import Menu
import Auxiliary
from Streamer.streamers import sifi_bioarmband_streamer
#from libemg.streamers import sifi_bioarmband_streamer
from libemg.data_handler import OnlineDataHandler
import time
import tomllib
import shutil
import os

#To-do
# - Periodically check connection to armband and create an event if its not connected?
# - Create a README.md file
# - Calculate the power of the signal from each EMG channel, create a plot of the power to make sure the subjects use adequate muscle intensity
# - Add the ability to add/edit events in retrospect

if __name__ == "__main__":

    # Load configs and save config file
    try:

        config_file = "./config.toml"

        # Open the TOML file in read-binary mode
        with open(config_file, "rb") as file:
            config = tomllib.load(file)

        subject = config['subject']
        media_folder = config['media_folder']
        gestures = config['gestures']

        data_folder = f"data/{subject}"

        sgt_args={
            'media_folder': media_folder,
            'data_folder': data_folder,
            'num_reps': config['sgt_args']['num_reps'],
            'rep_time': config['sgt_args']['rep_time'],
            'rest_time': config['sgt_args']['rest_time'],
            'auto_advance': config['sgt_args']['auto_advance'], 
            'discrete': config['sgt_args']['discrete']
        }

        streamer_args = {
            "name": config["streamer"]["name"],
            "ecg": config["streamer"]["ecg"],
            "emg": config["streamer"]["emg"],
            "eda": config["streamer"]["eda"],
            "imu": config["streamer"]["imu"],
            "ppg": config["streamer"]["ppg"],
            "temperature": config["streamer"]["temperature"],
            "filtering": config["streamer"]["filtering"],
            "emg_notch_freq": config["streamer"]["emg_notch_freq"],
            "emg_bandpass": tuple(config["streamer"]["emg_bandpass"]),
            "eda_bandpass": tuple(config["streamer"]["eda_bandpass"]),
            "eda_freq": config["streamer"]["eda_freq"],
            "streaming": config["streamer"]["streaming"],
            "night_mode": config["streamer"]["night_mode"],
            "high_gain": config["streamer"]["high_gain"],
            "ecg_fs": config["streamer"]["ecg_fs"],
            "emg_fs": config["streamer"]["emg_fs"],
            "eda_fs": config["streamer"]["eda_fs"],
            "imu_fs": config["streamer"]["imu_fs"],
            "ppg_sps": config["streamer"]["ppg_sps"],
            "ppg_avg": config["streamer"]["ppg_avg"],
            "temperature_fs": config["streamer"]["temperature_fs"]
        }

        data_folder = f"data/{subject}"
        os.makedirs(data_folder, exist_ok=True)

        # Save a copy of the configuration used for this recording
        shutil.copy2(config_file, f"{data_folder}/config.toml")        

    except FileNotFoundError:
        print(f"Error: The configuration file was not found.")
    except tomllib.TOMLDecodeError:
        print("Error: Failed to parse TOML. Please check your file syntax.")  

    # Run program
    try:
        streamer, shared_memory = sifi_bioarmband_streamer(**streamer_args)
        #streamer, shared_memory = sifi_bioarmband_streamer(name="SifiBand_2F4C", filtering=False, streaming=True)

        odh = OnlineDataHandler(shared_memory)

        data, counts = odh.get_data()

        Auxiliary.download_gestures(gestures, media_folder, download_imgs=True)

        Menu(subject, data_folder, gestures, media_folder, sgt_args, streamer_args, odh=odh)

        odh.stop_all()
        streamer.terminate()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        odh.stop_all()
        streamer.terminate()