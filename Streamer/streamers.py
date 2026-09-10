import time
import socket
import pickle
import platform
import numpy as np

from multiprocessing import Process, Event, Lock
from Streamer._sifi_bridge_streamer import SiFiBridgeStreamer
from Streamer.shared_memory_manager import assign_shared_memory_locks


def sifi_bioarmband_streamer(
    name = None,
    shared_memory_items = None,
    ecg = False,
    emg = True, 
    eda = False,
    imu = False,
    ppg = False,
    temperature = False,
    filtering = True, 
    emg_notch_freq = 60,
    emg_bandpass = (20,450),
    eda_bandpass = (0,5),
    eda_freq = 0,
    streaming = True,
    night_mode = False,
    high_gain = False,
    mac = None,
    ecg_fs = 500,
    emg_fs = 1600,
    eda_fs = 50,
    imu_fs = 50,
    ppg_sps = 50,
    ppg_avg = 1,
    temperature_fs = 1
):
    """
    The streamer for the SiFi BioArmband.
    
    This function connects to SiFi Bridge and streams its data to the SharedMemory.
    
    **Note**: The IMU keys are:
    
    - Acceleration: ax, ay, az
    - Quaternions: qw, qx, qy, qz
        
    Parameters
    ----------
    
    name: string, default = BioArmband
        The name of the Sifi Device. For example: BioArmband, BioPoint_v1_3, etc.
    shared_memory_items, default = []
        The key, size, datatype, and multiprocessing Lock for all data to be shared between processes.
    ecg, default = False
        Enable electrocardiography recording from the main sensor unit.
    emg, default = True
        Enable electromyography recording.
    eda, default = False
        Enable electrodermal recording.
    imu, default = False
        Enable inertial measurement unit recording
    ppg, default = False
        The flag to enable photoplethysmography recording
    temperature, default = False
        The flag to record skin temperature. The device reports temperature in its status packet, so this only controls whether it is stored in shared memory.
    filtering, default = True
        Enable on-device filtering, including bandpass filters and notch filters.
    emg_notch_freq, default = 60
        EMG notch filter frequency, useful for eliminating Mains power interference. Can be {None, 50, 60} Hz.
    emg_bandpass, default = (20, 450)
        The low and high cutoff frequency of the EMG bandpass filter.
    eda_bandpass, default = (0, 5)
        The low and high cutoff frequency of the EDA bandpass filter.
    eda_freq, default = 0
        The excitation signal frequency for EDA/BIOZ.  Setting an AC value may inject a lot of noise into the EMG sensor.
    streaming, default = True
        Whether to package the modalities together within packets for lower latency (sifibridge's low-latency mode), only supported for BioPoint v1.3 and up.
    night_mode, default = False
        Turn the device LEDs off during acquisition.
    high_gain, default = False
        Use more of the ECG/EMG ADC's dynamic range, at the cost of saturating more easily.
    mac, default = None:
        Optional MAC address the device to connect to, useful when multiple devices are in the vicinity and you want to connect to a specific one.
    ecg_fs, default = 500
        The ECG sampling rate (Hz). Can be {250, 500, 1000, 2000}.
    emg_fs, default = 1600
        The EMG sampling rate (Hz). Can be {500, 1000, 1600, 2000}.
    eda_fs, default = 50
        The EDA sampling rate (Hz). Can be {4, 8, 16, 32, 50}.
    imu_fs, default = 50
        The IMU sampling rate (Hz). Can be {25, 50, 100, 200}.
    ppg_sps, default = 50
        The PPG sampling rate (Hz). Can be {50, 100, 200, 400, 800}.
    ppg_avg, default = 1
        The PPG averaging factor. Can be {1, 2, 4, 8, 16, 32}. The effective PPG sampling rate (ppg_sps / ppg_avg) must be <= 400 Hz.
    temperature_fs, default = 1
        The temperature sampling rate (Hz). Can be {0.1, 1, 2, 10}.

    Returns
    ----------
    
    Object: streamer
        The sifi streamer process object.
    Object: shared memory
        The shared memory items list to be passed to the OnlineDataHandler.
    
    Examples
    ---------
    
    >>> streamer, shared_memory = sifibridge_streamer()
    """

    if shared_memory_items is None:
        shared_memory_items = []
        if emg:
            shared_memory_items.append(["emg",       (3000,8), np.double])
            shared_memory_items.append(["emg_count", (1,1),    np.int32])
        if imu:
            shared_memory_items.append(["imu",       (200,7), np.double])
            shared_memory_items.append(["imu_count", (1,1),    np.int32])
        if ecg:
            shared_memory_items.append(["ecg",       (1000,1), np.double])
            shared_memory_items.append(["ecg_count", (1,1),    np.int32])
        if eda:
            shared_memory_items.append(["eda",       (200,1), np.double])
            shared_memory_items.append(["eda_count", (1,1),    np.int32])
        if ppg:
            shared_memory_items.append(["ppg",       (200,4), np.double])
            shared_memory_items.append(["ppg_count", (1,1),    np.int32])
        if temperature:
            shared_memory_items.append(["temperature",       (100,1), np.double])
            shared_memory_items.append(["temperature_count", (1,1),   np.int32])

    assign_shared_memory_locks(shared_memory_items)

        
    sb = SiFiBridgeStreamer(
        name,
        shared_memory_items,
        ecg,
        emg,
        eda,
        imu,
        ppg,
        filtering,
        emg_notch_freq,
        emg_bandpass,
        eda_bandpass,
        eda_freq,
        streaming,
        night_mode,
        high_gain,
        mac,
        ecg_fs=ecg_fs,
        emg_fs=emg_fs,
        eda_fs=eda_fs,
        imu_fs=imu_fs,
        ppg_sps=ppg_sps,
        ppg_avg=ppg_avg,
        temperature_fs=temperature_fs,
        bioarmband=True
    )

    sb.start()
    return sb, shared_memory_items