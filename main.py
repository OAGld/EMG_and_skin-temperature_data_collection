from menu import Menu
import Auxiliary
from libemg.streamers import myo_streamer, sifi_bioarmband_streamer
from libemg.data_handler import OnlineDataHandler, OfflineDataHandler
from libemg.filtering import Filter
import sifi_bridge_py as sbp

def sifi_bioarmband_setup():
    sb = sbp.SifiBridge()

    sb.list_devices(sbp.ListSources.BLE)

    sb.connect("SifiBand_2F4C")

    sf = sb.configure_sampling_freqs()
    #print(sf)
    cr = sb.set_ble_power(sbp.BleTxPower.MEDIUM)
    #print(cr)

    sb.set_channels(ecg=True, emg=True, eda=True, imu=True, ppg=True)

    sb.set_filters(False)

    info = sb.show()
    print(info)

    sb.stop()
    sb.disconnect()



if __name__ == "__main__":

    #sifi_bioarmband_setup()

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
        streamer, shared_memory = sifi_bioarmband_streamer(name="SifiBand_2F4C", ecg=False, emg=True, eda=False, imu=False, ppg=False, filtering=False)
        #streamer, shared_memory = myo_streamer()
        odh = OnlineDataHandler(shared_memory)

        channels = [0, 1, 2, 3, 4, 5, 6, 7]
        channels = [0, 2, 3, 4]
        y_axis = ["y", "axis"]

        #odh.visualize_channels(channels=channels, num_samples=2000, y_axes=y_axis)

        Auxiliary.download_gestures(gestures, media_folder, download_imgs=True)

        Menu(subject, data_folder, gestures, media_folder, sgt_args, odh=odh)

        odh.stop_all()
        streamer.terminate()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        odh.stop_all()
        streamer.terminate()