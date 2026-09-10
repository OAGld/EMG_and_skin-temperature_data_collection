import time
import sifi_bridge_py as sbp

def sifi_bioarmband_setup():
    sb = sbp.SifiBridge()

    ble_devices = sb.list_devices(sbp.ListSources.BLE)
    print(f"Found: {ble_devices}")
    sb.connect("SifiBand_2F4C")

    info = sb.show()
    print(f"Connected: {info['connected']}")
    print(f"MAC: {info.get('mac')}")

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

    # Create bridge instance
    sb = sbp.SifiBridge()

    # Connect to the first available SiFi device (BioPoint or SiFi Band)
    sb.connect()

    # Sensors are off by default. Turn the ECG sensor on, then set its
    # filter parameters (500 Hz sampling rate).
    #sb.set_channels(ecg=True, emg=True, eda=True, imu=True, ppg=True)

    # Start acquisition
    sb.start()


    #packet = sb.get_data_with_key(["data", "temperature"])
    #print(f"Received {packet['packet_type']} packet")

    # Collect for 10 seconds
    start_time = time.time()
    data_buffer = []

    try:
        while time.time() - start_time < 3:
            packet = sb.get_data()  # Get any packet
            data_buffer.append(packet)
            print(f"Received {packet['packet_type']} packet")
            #print(f"packet: {packet}")

    except KeyboardInterrupt:
        print("Stopped by user")

    finally:
        sb.stop()
        sb.disconnect()
        print(f"Collected {len(data_buffer)} packets")
