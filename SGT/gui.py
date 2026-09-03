import dearpygui.dearpygui as dpg
from SGT._data_collection_panel import DataCollectionPanel
import inspect
import time
import os
import json
from os import walk
from libemg.data_handler import OnlineDataHandler, OfflineDataHandler
from libemg.streamers import myo_streamer, sifi_bioarmband_streamer

class GUI:
    """
    The Screen Guided Training module. 

    By default, this module has two purposes: 
    (1) Launching a Screen Guided Training window. 
    (2) Downloading gesture sets from our library of gestures located at:
    https://github.com/libemg/LibEMGGestures

    Parameters
    ----------
    online_data_handler: OnlineDataHandler
        Online data handler used for acquiring raw EMG data.
    args: dic, default={'media_folder': 'images/', 'data_folder':'data/', 'num_reps': 3, 'rep_time': 5, 'rest_time': 3, 'auto_advance': True, 'discrete': False}
        The dictionary that defines the SGT window. Keys are: 'media_folder',
        'data_folder', 'num_reps', 'rep_time', 'rest_time', 'auto_advance', and 'discrete'. All media (i.e., images and videos) in 'media_folder' will be played in alphabetical order.
        For video files, a matching labels file of the same name will be searched for and added to the 'data_folder' if found.
        'rep_time' is only used for images since the duration of videos is automatically calculated based on
        the number of frames (assumed to be 24 FPS). When 'discrete' is True, recording is controlled by
        holding the spacebar instead of using a timer - recording starts when spacebar is pressed and
        stops when released.  
    width: int, default=1920
        The width of the SGT window. 
    height: int, default=1080
        The height of the SGT window.
    gesture_width: int, default=500
        The width of the embedded gesture image/video.
    gesture_height: int, default=500
        The height of the embedded gesture image/video.
    clean_up_on_call: Boolean, default=False
        If true, this will cleanup (and kill) the streamer reference.
    """
    def __init__(self, 
                 args,
                 events_file,
                 width=1920,
                 height=1080,
                 debug=False,
                 gesture_width = 500,
                 gesture_height = 500,
                 clean_up_on_kill=False):
        
        self.width = width 
        self.height = height 
        self.debug = debug
        self.events_file = events_file
        self.args = args
        self.video_player_width = gesture_width
        self.video_player_height = gesture_height
        self.clean_up_on_kill = clean_up_on_kill
        self._install_global_fields()

    def start_gui(self):
        """
        Launches the Screen Guided Training UI.
        """
        self._window_init()
        
    def _install_global_fields(self):
        # self.global_fields = ['offline_data_handlers', 'online_data_handler']
        self.offline_data_handlers = []   if 'offline_data_handlers' not in self.args.keys() else self.args["offline_data_handlers"]
        self.offline_data_aliases  = []   if 'offline_data_aliases'  not in self.args.keys() else self.args["offline_data_aliases"]

    def _window_init(self):
        dpg.create_context()
        dpg.create_viewport(title="LibEMG",
                            width=self.width,
                            height=self.height)

        # Scale UI based on viewport height (base: 1080p -> 18pt font)
        self.ui_scale = self.height / 1080.0
        font_size = int(18 * self.ui_scale)

        # Load a proper TTF font for crisp text at any size
        font_paths = [
            "/System/Library/Fonts/SFNS.ttf",           # macOS San Francisco
            "/System/Library/Fonts/Helvetica.ttc",      # macOS Helvetica
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            "C:/Windows/Fonts/segoeui.ttf",             # Windows
        ]
        with dpg.font_registry():
            font_loaded = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    default_font = dpg.add_font(font_path, font_size)
                    font_loaded = True
                    break
            if not font_loaded:
                # Fallback: scale the default bitmap font (lower quality)
                default_font = None
                dpg.set_global_font_scale(self.ui_scale)
        if font_loaded:
            dpg.bind_font(default_font)

        dpg.setup_dearpygui()

        self._file_menu_init()

        dpg.set_exit_callback(self._on_window_close)

        dpg.show_viewport()

        dpg.start_dearpygui()

        dpg.destroy_context()


    def _file_menu_init(self):

        with dpg.viewport_menu_bar():
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="Exit", callback=lambda: dpg.stop_dearpygui())
                
            with dpg.menu(label="Data"):
                dpg.add_menu_item(label="Collect Data", callback=self._data_collection_callback)

    def _data_collection_callback(self):
        panel_arguments = list(inspect.signature(DataCollectionPanel.__init__).parameters)
        passed_arguments = {i: self.args[i] for i in self.args.keys() if i in panel_arguments}
        self.dcp = DataCollectionPanel(**passed_arguments, gui=self, video_player_width=self.video_player_width, video_player_height=self.video_player_height)
        self.dcp.spawn_configuration_window()

    def _on_window_close(self):
        if self.clean_up_on_kill:
            print("Window is closing. Performing clean-up...")
            if 'streamer' in self.args.keys():
                self.args['streamer'].signal.set()
            time.sleep(3)