import json
import time
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
import pandas as pd
import matplotlib.pyplot as plt
import os
from SGT.gui import GUI
import multiprocessing
from Auxiliary import plot_data_ext
from libemg.data_handler import OfflineDataHandler, RegexFilter
from libemg.feature_extractor import FeatureExtractor

def run_sgt(events_file, sgt_args):
    training_ui = GUI(events_file=events_file, args=sgt_args, gesture_height=500, gesture_width=500)
    training_ui.start_gui()

class Menu:

    # ============================================================
    # Auxiliary
    # ============================================================
    def __init__(self, subject, data_folder, gestures, media_folder, sgt_args, streamer_args, odh):
        self.odh = odh
        self.subject = subject
        self.data_folder = data_folder
        self.gestures = gestures
        self.media_folder = media_folder
        self.sgt_args = sgt_args
        self.filtering = streamer_args["filtering"]

        self.emg_file = f"{self.data_folder}emg.csv"
        self.events_file = f"{self.data_folder}events.json"
        self.temperature_file = f"{self.data_folder}temperature.csv"
        os.makedirs(self.data_folder, exist_ok=True)

        self.recording_start = None
        self.recording_end = None

        # Session info state
        self.comments = []
        self.info_filepath = None

        self.create_gui()

    def analyze_data(self):

        ofdh  = OfflineDataHandler()
        fe = FeatureExtractor()

        with open(self.emg_file, "r") as f:
            row_count = sum(1 for line in f)

        if row_count < 50001:
            print("Not enough data to analyze. Please record more data.")
        else:
            skiprows = row_count - 50000

            emg_filter = RegexFilter(
                left_bound="",       # nothing before "emg"
                right_bound=".csv",  # "emg" is immediately followed by ".csv"
                values=["emg"],      # the only value we're matching
                description=""       # empty string = don't store this as metadata, just filter
            )
            ofdh.get_data(folder_location=self.data_folder, regex_filters=[emg_filter], delimiter=" ", skiprows=skiprows, data_column=[1, 2, 3, 4, 5, 6, 7, 8])
            data_windows, data_meta = ofdh.parse_windows(window_size=50, window_increment=10)

            rms_values = fe.getRMSfeat(data_windows)

            num_channels = rms_values.shape[1]
            fig, ax = plt.subplots(figsize=(10, 5))
            for ch in range(num_channels):
                ax.plot(rms_values[:, ch], label=f"Channel {ch + 1}")

            ax.set_xlabel("Window Index")
            ax.set_ylabel("RMS Amplitude")
            ax.set_title("RMS Signal Strength per Window")
            ax.legend(loc="upper right", ncol=2, fontsize="small")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            plt.show()

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
        self.odh.visualize()

    # Update the color text of the status indicators
    def update_status_colours(self):

        # Recording
        if self.recording_status.get() == "RECORDING":
            self.recording_cell.config(bg="green") 
            self.recording_label.config(bg="green", fg="black")
        else:
            self.recording_cell.config(bg="red")
            self.recording_label.config(bg="red", fg="black")

        # Streaming
        if self.streaming_status.get() == "STREAMING":
            self.streaming_cell.config(bg="green")
            self.streaming_label.config(bg="green", fg="black")
        else:
            self.streaming_cell.config(bg="red")
            self.streaming_label.config(bg="red", fg="black")

    def check_connection(self):
        
        streaming = self.odh._check_streaming()
        if streaming:
            self.streaming_status.set("STREAMING")
        else:
            self.streaming_status.set("NOT STREAMING")
            self.create_event("Lost connection to device")

        self.update_status_colours()
        self.window.after(1000, self.check_connection)

    def reset(self):
        self.odh.reset()

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
    # Session info
    # ============================================================
 
    def build_info_header(self):
        """Build the header block containing the session fields."""
 
        return (
            f"Subject: {self.subject}\n"
            f"Age: {self.age_entry.get()}\n"
            f"Gender: {self.gender_entry.get()}\n"
            f"Date: {self.date_entry.get()}\n"
            f"Time: {self.time_entry.get()}\n"
            f"Outside temperature: {self.outside_temp_entry.get()}\n"
            f"\n--- Comments ---\n"
        )
 
    def save_session_info(self):
        """Write the subject, age, gender, date, time, outside temperature and all
        comments collected so far to the information file, named by the user in
        the file name field, always saved inside self.data_folder."""
 
        filename = self.filename_entry.get().strip()
 
        if not filename:
            messagebox.showerror("Error", "Please enter a file name.")
            return
 
        if not filename.lower().endswith(".txt"):
            filename += ".txt"
 
        filepath = os.path.join(self.data_folder, filename)
        self.info_filepath = filepath
        self.info_file_label_var.set(f"File: {filename}")
 
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.build_info_header())
                for comment_line in self.comments:
                    f.write(comment_line + "\n")
 
            messagebox.showinfo("Saved", f"Session info saved to:\n{filepath}")
 
        except OSError as e:
            messagebox.showerror("Error", f"Could not write to file:\n{e}")
 
    def add_comment(self):
        """Add a timestamped comment to the log. If an information file has
        already been chosen, the comment is appended to it immediately, so
        comments keep accumulating in the same file over the session."""
 
        comment_text = self.comment_entry.get("1.0", tk.END).strip()
 
        if not comment_text:
            return
 
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        comment_line = f"[{timestamp}] {comment_text}"
 
        self.comments.append(comment_line)
        self.comments_display.insert(tk.END, comment_line)
 
        # If a file has already been chosen, append immediately so nothing is lost
        if self.info_filepath is not None:
            try:
                with open(self.info_filepath, "a", encoding="utf-8") as f:
                    f.write(comment_line + "\n")
            except OSError as e:
                messagebox.showerror("Error", f"Could not append to file:\n{e}")
 
        self.comment_entry.delete("1.0", tk.END)

 

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
        self.window.geometry("950x950")

        self.recording_status = tk.StringVar(value="NOT RECORDING")
        self.streaming_status = tk.StringVar(value="NOT STREAMING")

        # Check connection every second
        self.window.after(1000, self.check_connection)

        # ========================================================
        # Title
        # ========================================================

        tk.Label(
            self.window,
            text="EMG Recording",
            font=("Arial", 20)
        ).pack(pady=(20, 15))


        # ========================================================
        # Indicators
        # ========================================================

        indicator_frame = tk.Frame(self.window)
        indicator_frame.pack(pady=(0, 15))

        # Recording cell
        self.recording_cell = tk.Frame(
            indicator_frame,
            relief=tk.RIDGE,
            borderwidth=2,
            padx=15,
            pady=8
        )
        self.recording_cell.pack(side=tk.LEFT, padx=5)

        self.recording_label = tk.Label(
            self.recording_cell,
            textvariable=self.recording_status,
            font=("Arial", 14)
        )
        self.recording_label.pack()

        # Streaming cell
        self.streaming_cell = tk.Frame(
            indicator_frame,
            relief=tk.RIDGE,
            borderwidth=2,
            padx=15,
            pady=8
        )
        self.streaming_cell.pack(side=tk.LEFT, padx=5)

        self.streaming_label = tk.Label(
            self.streaming_cell,
            textvariable=self.streaming_status,
            font=("Arial", 14)
        )
        self.streaming_label.pack()


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
        # Session info
        # ========================================================
 
        info_frame = tk.LabelFrame(
            main_frame,
            text="Session Info",
            font=("Arial", 12),
            padx=15,
            pady=15
        )
 
        info_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 10)
        )
 
        # Subject header
        tk.Label(
            info_frame,
            text=f"Subject: {self.subject}",
            font=("Arial", 14, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
 
        # Age
        tk.Label(info_frame, text="Age:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.age_entry = tk.Entry(info_frame, width=18)
        self.age_entry.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # Gender
        tk.Label(info_frame, text="Gender:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        self.gender_entry = tk.Entry(info_frame, width=18)
        self.gender_entry.grid(row=4, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # Date
        tk.Label(info_frame, text="Date:").grid(row=5, column=0, sticky="w", padx=5, pady=3)
        self.date_entry = tk.Entry(info_frame, width=18)
        self.date_entry.insert(0, time.strftime("%Y-%m-%d"))
        self.date_entry.grid(row=6, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # Time
        tk.Label(info_frame, text="Time:").grid(row=7, column=0, sticky="w", padx=5, pady=3)
        self.time_entry = tk.Entry(info_frame, width=18)
        self.time_entry.insert(0, time.strftime("%H:%M"))
        self.time_entry.grid(row=8, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # Outside temperature
        tk.Label(info_frame, text="Outside temp (°C):").grid(row=9, column=0, sticky="w", padx=5, pady=3)
        self.outside_temp_entry = tk.Entry(info_frame, width=18)
        self.outside_temp_entry.grid(row=10, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # Comment entry
        tk.Label(info_frame, text="Comment:").grid(row=11, column=0, sticky="w", padx=5, pady=3)
        self.comment_entry = tk.Text(info_frame, width=22, height=3)
        self.comment_entry.grid(row=12, column=0, sticky="ew", padx=5, pady=(0, 5))
 
        tk.Button(
            info_frame,
            text="Add Comment",
            width=18,
            command=self.add_comment
        ).grid(row=13, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # Comments log display
        tk.Label(info_frame, text="Comments log:").grid(row=14, column=0, sticky="w", padx=5, pady=3)
        self.comments_display = tk.Listbox(info_frame, width=22, height=5)
        self.comments_display.grid(row=15, column=0, sticky="ew", padx=5, pady=(0, 8))
 
        # File name + save
        tk.Label(info_frame, text="File name (saved in data folder):").grid(
            row=16, column=0, sticky="w", padx=5, pady=3
        )
        self.filename_entry = tk.Entry(info_frame, width=18)
        self.filename_entry.insert(0, f"_info.txt")
        self.filename_entry.grid(row=17, column=0, sticky="ew", padx=5, pady=(0, 5))
 
        self.info_file_label_var = tk.StringVar(value="Not saved yet")
        tk.Label(info_frame, textvariable=self.info_file_label_var, fg="gray", wraplength=180).grid(
            row=18, column=0, sticky="w", padx=5, pady=(0, 5)
        )
 
        tk.Button(
            info_frame,
            text="Save Info to File",
            width=18,
            height=2,
            command=self.save_session_info
        ).grid(row=19, column=0, sticky="ew", padx=5, pady=(5, 0))


        # ========================================================
        # controls
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
            column=1,
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
            text="Analyze data",
            width=20,
            height=2,
            command=self.analyze_data
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Screen guided gesturing",
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
            text="Reset data",
            width=20,
            height=2,
            command=self.reset
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Exit",
            width=20,
            height=2,
            command=self.exit_program
        ).pack(pady=20)


        # ========================================================
        # events
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
            column=2,
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