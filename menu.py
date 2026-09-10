import json
import time
import tkinter as tk
from tkinter import simpledialog, messagebox
import pandas as pd
import matplotlib.pyplot as plt
import os
from SGT.gui import GUI
import multiprocessing
from Auxiliary import plot_data_ext

def run_sgt(events_file, sgt_args):
    training_ui = GUI(events_file=events_file, args=sgt_args, gesture_height=500, gesture_width=500)
    training_ui.start_gui()

class Menu:

    def __init__(self, subject, data_folder, gestures, media_folder, sgt_args, odh):
        self.odh = odh
        self.subject = subject
        self.data_folder = data_folder
        self.gestures = gestures
        self.media_folder = media_folder
        self.sgt_args = sgt_args

        self.emg_file = f"{self.data_folder}emg.csv"
        self.events_file = f"{self.data_folder}events.json"
        os.makedirs(self.data_folder, exist_ok=True)

        self.recording_start = None
        self.recording_end = None

        self.create_gui()

    def analyze_device(self):
        self.odh.analyze_hardware()

    def start_sgt(self):

        process = multiprocessing.Process(
            target=run_sgt,
            args=(self.events_file, self.sgt_args)
        )

        process.start()

        self.sgt_process = process

    def start_visualize(self):
        self.odh.visualize_channels(channels=[0, 2, 3, 4], num_samples=2000)

    # ============================================================
    # Recording
    # ============================================================

    def start_recording(self):

        self.recording_start = time.time()

        self.create_event("Start recording")

        self.odh.log_to_file(
            file_path=self.data_folder,
            timestamps=True
        )

        self.recording_status.set("RECORDING")

    def stop_recording(self):

        self.recording_end = time.time()

        self.odh.stop_all()
        self.create_event("Stop recording")

        self.recording_status.set("NOT RECORDING")


    # ============================================================
    # Events
    # ============================================================

    def create_event(self, event_name):

        if event_name == "Custom event":

            event_name = simpledialog.askstring(
                "Input Request",
                "Name the event:"
            )

            if not event_name:
                return

        event = {
            "timestamp": time.time(),
            "event": event_name
        }

        # Save immediately
        with open(self.events_file, "a") as f:
            json.dump(event, f)
            f.write("\n")


    # ============================================================
    # Plot
    # ============================================================
    def plot_data(self):
        plot_data_ext(self)

    # ============================================================
    # Exit
    # ============================================================

    def exit_program(self):
        self.create_event("Exit program")
        self.window.destroy()

    # ============================================================
    # GUI
    # ============================================================

    def create_gui(self):

        self.window = tk.Tk()
        self.window.title("EMG Recording")
        self.window.geometry("650x650")

        self.recording_status = tk.StringVar(
            value="NOT RECORDING"
        )

        # ========================================================
        # Title
        # ========================================================

        tk.Label(
            self.window,
            text="EMG Recording",
            font=("Arial", 20)
        ).pack(pady=(20, 15))


        # ========================================================
        # Recording indicator
        # ========================================================

        tk.Label(
            self.window,
            textvariable=self.recording_status,
            font=("Arial", 14)
        ).pack(pady=(0, 15))


        # ========================================================
        # Main container
        # ========================================================

        main_frame = tk.Frame(self.window)

        main_frame.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=5
        )

        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)


        # ========================================================
        # Left side - controls
        # ========================================================

        control_frame = tk.LabelFrame(
            main_frame,
            text="Controls",
            font=("Arial", 12),
            padx=15,
            pady=15
        )

        control_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 10)
        )

        tk.Button(
            control_frame,
            text="Analyze device",
            width=20,
            height=2,
            command=self.analyze_device
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Start recording",
            width=20,
            height=2,
            command=self.start_recording
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Visualize",
            width=20,
            height=2,
            command=self.start_visualize
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Start screen guided collection",
            width=20,
            height=2,
            command=self.start_sgt
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Stop recording",
            width=20,
            height=2,
            command=self.stop_recording
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Plot data",
            width=20,
            height=2,
            command=self.plot_data
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Exit",
            width=20,
            height=2,
            command=self.exit_program
        ).pack(pady=20)


        # ========================================================
        # Right side - events
        # ========================================================

        event_frame = tk.LabelFrame(
            main_frame,
            text="Events",
            font=("Arial", 12),
            padx=15,
            pady=15
        )

        event_frame.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(10, 0)
        )

        event_frame.columnconfigure(0, weight=1)
        event_frame.columnconfigure(1, weight=1)


        # ========================================================
        # Event buttons
        # ========================================================

        # Load gesture names from JSON
        with open(f"{self.media_folder}gesture_list.json", "r", encoding="utf-8") as f:
            gesture_mapping = json.load(f)


        # Create gesture buttons automatically
        for index, gesture_id in enumerate(self.gestures):

            gesture_name = gesture_mapping.get(str(gesture_id))

            if gesture_name is None:
                gesture_name = f"Unknown gesture ({gesture_id})"

            tk.Button(
                event_frame,
                text=gesture_name,
                width=18,
                height=2,
                command=lambda name=gesture_name: self.create_event(name)
            ).grid(
                row=index // 2,
                column=index % 2,
                padx=5,
                pady=7,
                sticky="ew"
            )


        # Fixed event buttons
        event_buttons = [
            ("Stop gesture", "Stop gesture"),
            ("Enter sauna", "Enter sauna"),
            ("Exit sauna", "Exit sauna"),
            ("Enter fridge", "Enter fridge"),
            ("Exit fridge", "Exit fridge"),
            ("Move location", "Move location"),
            ("Custom event", "Custom event"),
        ]

        # Start after the gesture buttons
        start_index = len(self.gestures)

        for index, (button_text, event_name) in enumerate(event_buttons):

            button_index = start_index + index

            tk.Button(
                event_frame,
                text=button_text,
                width=18,
                height=2,
                command=lambda name=event_name: self.create_event(name)
            ).grid(
                row=button_index // 2,
                column=button_index % 2,
                padx=5,
                pady=7,
                sticky="ew"
            )

        # ========================================================
        # Start GUI
        # ========================================================

        self.window.mainloop()