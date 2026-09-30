from abc import ABC, abstractmethod
from typing import Callable, Sequence
import numpy as np
import numpy.typing as npt
import pandas as pd
import os
import re
import time
import math
import wfdb
import copy
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.axes import Axes
from scipy.ndimage import zoom
from scipy.signal import decimate
from matplotlib import pyplot
from matplotlib.animation import FuncAnimation
from pathlib import Path
from glob import glob
from multiprocessing import Process
from multiprocessing import Process, Event
from libemg.feature_extractor import FeatureExtractor
from libemg.shared_memory_manager import SharedMemoryManager
from scipy.signal import welch
from libemg.utils import get_windows, _get_fn_windows, _get_mode_windows, make_regex

class DataHandler:
    def __init__(self):
        self.data = []
        pass

    def _get_num_channels(self, data):
        return len(data[0])

    def _get_sampling_rate(self, data, time):
        return int(math.ceil(len(data)/time))

    def _get_resolution(self, data):
        return int(math.ceil(math.log2(len(np.unique(data)))))
    
    def _get_max_value(self, data):
        return np.max(data)
    
    def _get_min_value(self, data):
        return np.min(data)
    
class OnlineDataHandler(DataHandler):
    """OnlineDataHandler class - responsible for collecting data streamed over shared memory.

    This class is extensible to any device as long as the data is being streamed over shared memory.
    By default this will start writing to an array of EMG data stored in memory.

    Parameters
    ----------
    shared_memory_items: Object
        The shared memory object returned from the streamer.
    channel_mask: list or None (optional), default=None
        Mask of active channels to use online. Allows certain channels to be ignored when streaming in real-time. If None, all channels are used.
        Defaults to None.
    """
    def __init__(self, shared_memory_items, channel_mask = None):
        self.shared_memory_items = shared_memory_items
        self.prepare_smm()
        self.log_signal = Event()
        self.visualize_signal = Event()        
        self.fi = None
        self.channel_mask = channel_mask
    
    def prepare_smm(self):
        self.modalities = []
        self.smm = SharedMemoryManager()
        for i in self.shared_memory_items:
            counter = 0
            while not self.smm.find_variable(*i):
                counter += 1
                time.sleep(0.5)
                if counter > 5:
                    print(f"Not finding key {i[0]} in shared memory...waiting.")
            if "_count" in i[0]:
                continue
            self.modalities.append(i[0])

    def stop_all(self):
        """Terminates the processes spawned by the ODH.
        """
        self.stop_log()
        self.stop_visualize()

    def stop_log(self):
        self.log_signal.set()
        time.sleep(0.5)
        self.log_signal.clear()

    def stop_visualize(self):
        self.visualize_signal.set()
        time.sleep(0.5)
        self.visualize_signal.clear()

    def install_filter(self, fi):
        """Install a filter to be used on the online stream of data.
        
        Parameters
        ----------
        fi: libemg.filter object
            The filter object that you'd like to run on the online data.
        """
        self.fi = fi

    def install_channel_mask(self, mask):
        """Install a channel mask to isolate certain channels for online streaming.

        Parameters
        ----------
        mask: list or None (optional), default=None
            Mask of active channels to use online. Allows certain channels to be ignored when streaming in real-time. If None, all channels are used.
            Defaults to None.
        """
        self.channel_mask = mask


    def analyze_hardware(self, analyze_time=10):
        """Analyzes several metrics from the hardware:
        (1) sampling rate
        (2) resolution
        (3) min val
        (4) max val
        (5) number of channels

        Parameters
        ----------
        analyze_time: int (optional), default=10 (seconds)
            The time in seconds that you want to analyze the device for. 
        """
        if not self._check_streaming():
            return

        self.reset()
        st = time.time()
        print("Starting analysis " + "(" + str(analyze_time) + "s)... We suggest that you elicit varying contractions and intensities to get an accurate analysis.")
        counters = {}
        data = {}
        for mod in self.modalities:
            counters[mod]=0
            data[mod]=[]
        while(time.time() - st < analyze_time):
            vals, count = self.get_data()
            for mod in self.modalities:
                num_new_samples = count[mod][0][0]-counters[mod]
                if num_new_samples > 0:
                    data[mod] = [vals[mod][:num_new_samples,:]] + data[mod]
                    counters[mod] += num_new_samples

        for key in data.keys():
            print('--------- ' + str(key) + ' ---------')
            t_data = np.vstack(data[key])
            print("Sampling Rate: " + str(self._get_sampling_rate(t_data,analyze_time)))
            print("Num Channels: " + str(self._get_num_channels(t_data)))
            print("Max Value: " + str(self._get_max_value(t_data)))
            print("Min Value: " + str(self._get_min_value(t_data)))
            print("Resolution: " + str(self._get_resolution(t_data)) + " bits")
        
        print("Analysis sucessfully complete. ODH process has stopped.")

    def visualize(self, num_samples=500, block=True):
        """Visualize the incoming raw EMG in a plot (all channels together).

        Parameters
        ----------
        num_samples: int (optional), default=500
            The number of samples to show in the plot.
        block: Boolean (optional), default=False
            Blocks the main thread if True.
        """
        if block:
            self._visualize(num_samples)
        else:
            p = Process(target=self._visualize, kwargs={"num_samples":num_samples}, daemon=True)
            p.start()

    def _visualize(self, num_samples):
        self.prepare_smm()

        pyplot.style.use('ggplot')
        plots = []
        fig, ax = pyplot.subplots(len(self.modalities), 1,squeeze=False)
        def on_close(event):
            self.visualize_signal.set()
        fig.canvas.mpl_connect('close_event', on_close)
        fig.suptitle('Raw Data', fontsize=16)
        for i,mod in enumerate(self.modalities):
            num_channels = self.smm.get_variable(mod).shape[1]
            for j in range(0,num_channels):
                plots.append(ax[i][0].plot([],[],label=mod+"_CH"+str(j+1)))
        
        fig.legend()
        
        def update(frame):
            data, _ = self.get_data(N=0,filter=True)
            line = 0
            for i, mod in enumerate(self.modalities):
                for j in range(data[mod].shape[1]):
                    data[mod][:,j] = data[mod][:,j] - np.mean(data[mod][:,j])
                inter_channel_amount = 1.5 * np.max(data[mod])
                if len(data[mod]) > num_samples:
                    data[mod] = data[mod][:num_samples,:]
                if len(data[mod]) > 0:
                    x_data = list(range(0,data[mod].shape[0]))
                    num_channels = data[mod].shape[1]
                    for j in range(0,num_channels):
                        y_data = data[mod][:,j]
                        plots[line][0].set_data(x_data, y_data +inter_channel_amount*j)
                        line += 1
            for i in range(len(self.modalities)):
                ax[i][0].relim()
                ax[i][0].autoscale_view()
                ax[i][0].set_title(self.modalities[i])
            return plots,
    
        while True:
            animation = FuncAnimation(fig, update, interval=500, repeat=False)
            pyplot.show()
            if self.visualize_signal.is_set():
                print("ODH->visualize ended.")
                break

    def visualize_channels(self, channels, num_samples=500, y_axes=None):
        """Visualize individual channels (each channel in its own plot).

        Parameters
        ----------
        channels: list
            A list of channels to graph indexing starts at 0.
        num_samples: int (optional), default=500
            The number of samples to show in the plot.
        y_axes: list (optional)
            A list of two elements consisting of the y-axes.
        """
        self.prepare_smm()
        pyplot.style.use('ggplot')
        while not self._check_streaming():
            pass
        emg_plots = []
        fig, ax = pyplot.subplots()
        fig.suptitle('Raw Data', fontsize=16)
        for i in range(0,len(channels)):
            emg_plots.append(ax.plot([],[],label="CH"+str(channels[i])))

        def update(frame):
            data, _ = self.get_data()
            data = data['emg']
            data = data[:,channels]
            inter_channel_amount = 1.5 * np.max(data)
            if len(data) > num_samples:
                data = data[:num_samples,:]
            if len(data) > 0:
                x_data = list(range(0,data.shape[0]))
            
                for i in range(data.shape[1]):
                    y_data = data[:,i]
                    emg_plots[i][0].set_data(x_data, y_data +inter_channel_amount*i)
                fig.gca().relim()
                fig.gca().autoscale_view()
            return emg_plots,

        animation = FuncAnimation(fig, update, interval=100)
        pyplot.show()
    
    def visualize_heatmap(self, num_samples = 500, feature_list = None, remap_function = None, cmap = None):
        """Visualize heatmap representation of EMG signals. This is commonly used to represent HD-EMG signals.

        Parameters
        ----------
        num_samples: int (optional), default=500
            The number of samples to average over (i.e., window size) when showing heatmap.
        feature_list: list or None (optional), default=None
            List of feature representations to extract, where each feature will be shown in a different subplot. 
            Compatible with all features in libemg.feature_extractor.get_feature_list() that return a single value per channel (e.g., MAV, RMS). 
            If a feature type that returns multiple values is passed, an error will be thrown. If None, defaults to MAV.
        remap_function: callable or None (optional), default=None
            Function pointer that remaps raw data to a format that can be represented by an image (such as np.reshape). Takes in an array and should return
            an array. If None, no remapping is done.
        cmap: colormap or None (optional), default=None
            matplotlib colormap used to plot heatmap.
        """
        # Create figure
        pyplot.style.use('ggplot')
        if not self._check_streaming():
            # Not reading any data
            return
        
        if feature_list is None:
            # Default to MAV
            feature_list = ['MAV']

        if cmap is None:
            cmap = cm.viridis   # colourmap to determine heatmap style
        
        def extract_data():
            data, _ = self.get_data()
            data = data['emg']
            if len(data) > num_samples:
                # Only look at the most recent num_samples samples (essentially extracting a single window)
                data = data[:num_samples]
            # Extract features along each channel
            windows = data[np.newaxis].transpose(0, 2, 1)   # add axis and tranpose to convert to (windows x channels x samples)
            fe = FeatureExtractor()
            feature_set_dict = fe.extract_features(feature_list, windows, array=False)
            assert isinstance(feature_set_dict, dict), f"Expected dictionary of features. Got: {type(feature_set_dict)}."
            if remap_function is not None:
                # Remap raw data to image format
                for key in feature_set_dict:
                    feature_set_dict[key] = remap_function(feature_set_dict[key]).squeeze() # squeeze to remove extra axis added for windows
            return feature_set_dict

        # Analyze data stream to determine min/max values for normalizing
        analyze_time = 5
        print(f"Analyzing data stream for {analyze_time} seconds to determine min/max values for each feature value. Please rest, then perform a contraction at max intensity.")
        start_time = time.time()
        normalization_values = {}
        while (time.time() - start_time) < analyze_time:
            features = extract_data()
            for feature, feature_data in features.items():
                if feature not in normalization_values.keys():
                    normalization_values[feature] = (feature_data.min(), feature_data.max())
                else:
                    old_min, old_max = normalization_values[feature]
                    current_min = min(old_min, feature_data.min())
                    current_max = max(old_max, feature_data.max())
                    normalization_values[feature] = (current_min, current_max)

        
        # Format figure
        sample_data = extract_data()    # access sample data to determine heatmap size
        fig, axs = plt.subplots(len(sample_data.keys()), 1)
        if isinstance(axs, Axes):
            axs = np.array([axs])
        fig.suptitle(f'HD-EMG Heatmap')
        plots = []
        for (feature_key, feature_data), ax in zip(sample_data.items(), axs):
            ax.set_title(f'{feature_key}')
            ax.set_xlabel('Electrode Row')
            ax.set_ylabel('Electrode Column')
            ax.grid(visible=False)  # disable grid
            ax.set_xticks(range(feature_data.shape[1]))
            ax.set_yticks(range(feature_data.shape[0]))
            im = ax.imshow(np.zeros(shape=feature_data.shape), cmap=cmap, animated=True)
            plt.colorbar(im)
            plots.append(im)
        plt.tight_layout()
            

        def update(frame):
            # Update function to produce live animation
            data = extract_data()
                
            if len(data) > 0:
                # Loop through feature plots
                for feature, plot in zip(data.items(), plots):
                    feature_key, feature_data = feature
                    feature_min, feature_max = normalization_values[feature_key]
                    # Normalize to properly display colours
                    normalized_data = (feature_data - feature_min) / (feature_max - feature_min)
                    # Convert to coloured map
                    heatmap_data = cmap(normalized_data)
                    plot.set_data(heatmap_data) # update plot
            return plots, 
        
        animation = FuncAnimation(fig, update, interval=100)
        pyplot.show()

    def visualize_feature_space(self, feature_dic, window_size, window_increment, sampling_rate, hold_samples=20, projection="PCA", classes=None, class_labels=None, normalize=True):
        """Visualize a live pca plot. This is reliant on previously collected training data.

        Parameters
        ----------
        feature_dic: dict
            A dictionary consisting of the different features acquired through screen guided training. This is the output from the 
            extract_features method.
        window_size: int
            The number of samples in a window. 
        window_increment: int
            The number of samples that advances before next window.
        sampling_rate: int
            The sampling rate of the device. This impacts the refresh rate of the plot. 
        hold_samples: int (optional), default=20
            The number of live samples that are shown on the plot.
        projection: string (optional), default=PCA
            The projection method. Currently, the only available option, is PCA.
        classes: list
            A list of classes that is associated with each feature index.
        class_labels: list
            A list of class labels for the legend. 
        normalize: boolean
            Whether the user wants to scale features to zero mean and unit standard deviation before projection (recommended).
        """
        from sklearn.decomposition import PCA
        pyplot.style.use('ggplot')
        feature_list = feature_dic.keys()
        fe = FeatureExtractor()

        if projection == "PCA":
            for i, k in enumerate(feature_dic.keys()):
                feature_matrix = feature_dic[k] if i == 0 else np.hstack((feature_matrix, feature_dic[k]))

            if normalize:
                feature_means = np.mean(feature_matrix, axis=0)
                feature_stds  = np.std(feature_matrix, axis=0)
                feature_matrix = (feature_matrix - feature_means) / feature_stds

            fig, ax = plt.subplots()
            pca = PCA(n_components=feature_matrix.shape[1]) 

            if classes is not None:
                class_list = np.unique(classes)
    
            train_data = pca.fit_transform(feature_matrix)
            if classes is not None:
                for c in class_list:
                    class_ids = classes == c
                    c_label = "tr "+str(int(c)),
                    if class_labels is not None:
                        c_label = class_labels[c]
                    ax.plot(train_data[class_ids,0], train_data[class_ids,1], marker='.', alpha=0.75, label=c_label, linestyle="None")
            else:
                ax.plot(train_data[:,0], train_data[:,1], marker=".", label="tr", linestyle="None")
            
            graph = ax.plot(0, 0, marker='+', color='black', alpha=0.75, label="new_data", linestyle="None")

            fig.legend()
            self.reset()

            pc1 = [] 
            pc2 = []      

            def update(frame):
                data, counts = self.get_data(N=window_size)
                if counts['emg'] > window_size:
                    data = data['emg'][::-1]
                    window = get_windows(data, window_size, window_size)
                    features = fe.extract_features(feature_list, window)
                    for i, k in enumerate(features.keys()):
                        formatted_data = features[k] if i == 0 else np.hstack((formatted_data, features[k]))
                    
                    if normalize:
                        formatted_data = (formatted_data-feature_means)/feature_stds

                    data = pca.transform(formatted_data)
                    pc1.append(data[0,0])
                    pc2.append(data[0,1])

                    pc1_data = pc1[-hold_samples:]
                    pc2_data = pc2[-hold_samples:]
                    graph[0].set_data(pc1_data, pc2_data)

                    ax.relim()
                    ax.autoscale_view()

            animation = FuncAnimation(fig, update, interval=(1000/sampling_rate * window_increment))
            plt.show()

    def get_data(self, N=0, filter=True):
        """Grab the data in the shared memory buffer across all modalities.
 
        Parameters
        ----------
        N : int
            Number of samples to grab from the shared memory items. If zero, grabs all data.
        filter: bool
            Apply the installed filters to the data prior to returning or not.
 
        Returns
        ----------
        val: dict
            A dictionary with keys corresponding to the modalities. Each key will have a np.ndarray of data returned.
        count: dict
            A dictionary with keys corresponding to the modalities. Each key will have an int corresponding to the number
            of samples received since the streamer began (or the last reset call).
        """
        val   = {}
        count = {}
        for mod in self.modalities:
            data = self.smm.get_variable(mod)
            if filter:
                if self.fi is not None:
                    if mod == "emg": # TODO: enable filter for each modality
                        data = self.fi.filter(data)
            if N != 0:
                val[mod]   = data[:N,:]
            else:
                val[mod]   = data[:,:]
            if self.channel_mask is not None:
                val[mod] = val[mod][:, self.channel_mask]
            count[mod] = self.smm.get_variable(mod+"_count")
        return val,count

    def reset(self, modality=None):
        """Reset the data within the shared memory buffer.
 
        Parameters
        ----------
        modality: str
            The modality that should be reset. If None, all modalities are reset.
        """
        if modality == None:
            modality = self.modalities
        else:
            modality = [modality]
        for mod in modality:
            self.smm.modify_variable(mod, lambda x: np.zeros_like(x))
            self.smm.modify_variable(mod+"_count", lambda x: np.zeros_like(x))

    def log_to_file(self, block=False, file_path='', timestamps=True):
        """Logs the raw data being read to a file.

        Parameters
        ----------
        block: bool (optional), default=False 
            If true, the main thread will be blocked. 
        file_path: int (optional), default=''
            The prefix to the file path that will be logged for each modality.
        timestamps: bool (optional), default=True
            If true, this will log the timestamps with each recording.
        """
        print("ODH->log_to_file begin.")
        self.file_path = file_path
        self.timestamps = timestamps
        if block:
            self._log_to_file()
            print("ODH->log_to_file ended.")
        else:
            p = Process(target=self._log_to_file, daemon=True)
            p.start()

    def _log_to_file(self):

        files = {}
        # start shared memory manager to access sensor
        self.smm = SharedMemoryManager()
        for item in self.shared_memory_items:
            self.smm.find_variable(*item)
        # initialize sample count for all modalities
        last_count = {}
        for m in self.modalities:
            last_count[m] = 0
        while True:
            timestamp = time.time()
            vals, counts = self.get_data(N=0, filter=False)
            for m in vals.keys():
                new_count       = counts[m][0,0]
                num_new_samples = new_count - last_count[m]
                new_samples     = vals[m][:num_new_samples,:]
                last_count[m] = new_count
                if num_new_samples:
                    if not m in files.keys():
                        files[m] = open(self.file_path + m + '.csv', "a", newline='')
                    if self.timestamps:
                        np.savetxt(files[m], np.hstack((np.ones((new_samples.shape[0],1))*timestamp, new_samples)))
                        # check to see if they're in the right order, or if they need to be reversed again!
                    else:
                        np.savetxt(files[m], new_samples)
            if self.log_signal.is_set():
                print("ODH->log_to_file ended.")
                break

    def _check_streaming(self, timeout=15):
        wt = time.time()
        emg_count = self.smm.get_variable("emg_count")
        while(True):
            emg_count2 = self.smm.get_variable("emg_count")
            if emg_count != emg_count2: 
                return True
            if time.time() - wt > timeout:
                print("Not reading any data.... Check hardware connection.")
                return False
            
    def start_listening(self):
        print("LibEMG>v1.0 no longer requires online_data_handler.start_listening().\nThis is deprecated.")
        pass