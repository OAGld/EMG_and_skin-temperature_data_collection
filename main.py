from menu import Menu
import Auxiliary
#from libemg.streamers import myo_streamer, sifi_bioarmband_streamer
from Streamer.streamers import sifi_bioarmband_streamer
from libemg.data_handler import OnlineDataHandler
from libemg.filtering import Filter
import sifi_bridge_py as sbp
import time

#To-do
# - Periodically check connection to armband and create an event if its not connected?

if __name__ == "__main__":

    #Define subject
    subject = "subject1"

    #Define data folder
    data_folder = f"data/{subject}/"

    media_folder = "gestures/"
    #What gestures to include
    gestures = [1,2,3]

    sgt_args={
        'media_folder': media_folder,
        'data_folder':data_folder,
        'num_reps': 1, 
        'rep_time': 5, 
        'rest_time': 3, 
        'auto_advance': True, 
        'discrete': False
    }

    try:
        streamer, shared_memory = sifi_bioarmband_streamer(name="SifiBand_2F4C", ecg=True, emg=True, emg_fs=2000, eda=True, imu=True, ppg=True, temperature=True, filtering=False, streaming=False)

        odh = OnlineDataHandler(shared_memory)

        time.sleep(3)

        data, counts = odh.get_data()

        Auxiliary.download_gestures(gestures, media_folder, download_imgs=True)

        Menu(subject, data_folder, gestures, media_folder, sgt_args, odh=odh)

        odh.stop_all()
        streamer.terminate()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        odh.stop_all()
        streamer.terminate()