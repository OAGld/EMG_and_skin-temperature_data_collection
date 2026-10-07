import json
import multiprocessing
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import simpledialog, messagebox

from Auxiliary import plot_data_ext, data_QA_continuous
from CustomLibEMG.gui import GUI


# ==================== Console output ====================

# Class to redirect stdout and stderr to a queue for GUI display
class TextRedirector:
    """File-like object that sends written text to a queue.
    The GUI drains the queue on its own timer, so it's safe even if
    print() is called from a background thread."""

    def __init__(self, q, original):
        self.q = q
        self.original = original  # keep the real stream so the console still gets output

    def write(self, text):
        self.q.put(text)
        if self.original is not None:
            self.original.write(text)

    def flush(self):
        if self.original is not None:
            self.original.flush()


# ==================== Screen guided gesturing ====================

# Runs in its own process, started by Menu.start_sgt
def run_sgt(events_file, sgt_args):
    training_ui = GUI(events_file=events_file, args=sgt_args, gesture_height=500, gesture_width=500)
    training_ui.start_gui()


class Menu:

    # ==================== Setup ====================

    def __init__(self, subject, data_folder, gestures, media_folder, sgt_args, streamer_args, odh):

        # ---------- Shared ----------
        self.odh = odh
        self.subject = subject
        self.data_folder = data_folder   # created by main.py

        # ---------- Status indicators ----------
        self.stream_timeout_s = 2       # seconds without new EMG samples before the band counts as disconnected
        self.last_emg_count = None      # emg_count at the previous connection check
        self.last_count_change = 0.0    # time.time() when emg_count last increased

        # ---------- Events ----------
        self.events_file = f"{self.data_folder}events.json"
        self.gestures = gestures
        self.media_folder = media_folder

        # ---------- Data quality ----------
        self.emg_fs = streamer_args["emg_fs"]
        self.qa = data_QA_continuous(self.odh, event_callback=self.create_event)

        # ---------- Screen guided gesturing ----------
        self.sgt_args = sgt_args

        # ---------- Plotting (read by plot_data_ext) ----------
        self.emg_file = f"{self.data_folder}emg.csv"
        self.temperature_file = f"{self.data_folder}temperature.csv"

        # ---------- Session info ----------
        self.comments = []
        self.info_filepath = None

        # Builds the window and blocks in the Tk mainloop until the window is closed
        self.create_gui()

    # ==================== GUI ====================

    def create_gui(self):

        # ---------- Shared: window ----------

        self.window = tk.Tk()
        self.window.title("EMG Recording")
        self.window.protocol("WM_DELETE_WINDOW", self.confirm_exit)
        self.window.geometry("950x950")

        # ---------- Shared: scrollable container ----------

        outer_frame = tk.Frame(self.window)
        outer_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer_frame, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Make the inner frame match the canvas width so widgets can expand horizontally
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas_window, width=e.width)
        )

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel scrolling (Windows/macOS use <MouseWheel>, Linux uses Button-4/5)
        def _on_mousewheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)   # Windows / macOS
        canvas.bind_all("<Button-4>", _on_mousewheel)     # Linux scroll up
        canvas.bind_all("<Button-5>", _on_mousewheel)     # Linux scroll down

        # From here on, everything is placed in `scrollable_frame` instead of `self.window`

        # ---------- Status indicators ----------

        self.recording_status = tk.StringVar(value="NOT RECORDING")
        self.streaming_status = tk.StringVar(value="NOT STREAMING")

        indicator_frame = tk.Frame(scrollable_frame)
        indicator_frame.pack(pady=(20, 15))

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

        # Check connection every second
        self.window.after(1000, self.check_connection)

        # ---------- Shared: main container (session info, controls, events) ----------

        main_frame = tk.Frame(scrollable_frame)

        main_frame.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=5
        )

        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # ---------- Session info ----------

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

        # ---------- Controls ----------

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
            text="Monitor data",
            width=20,
            height=2,
            command=self.monitor_data
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
            text="Set baseline",
            width=20,
            height=2,
            command=self.set_QA_baseline
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Analyze device",
            width=20,
            height=2,
            command=self.analyze_device
        ).pack(pady=8)

        tk.Button(
            control_frame,
            text="Exit",
            width=20,
            height=2,
            command=self.exit_program
        ).pack(pady=20)

        # ---------- Events ----------

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

        # Fixed event buttons (the button text is also the event name)
        event_names = [
            "Stop gesture",
            "Enter warm environment",
            "Exit warm environment",
            "Enter cold environment",
            "Exit cold environment",
            "Enter room temperature environment",
            "Exit room temperature environment",
            "Move location",
            "Custom event",
        ]

        # Start after the gesture buttons
        start_index = len(self.gestures)

        for index, event_name in enumerate(event_names):

            button_index = start_index + index

            tk.Button(
                event_frame,
                text=event_name,
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

        # ---------- Console output ----------

        console_frame = tk.LabelFrame(
            scrollable_frame,
            text="Console output",
            font=("Arial", 12),
            padx=10,
            pady=10
        )
        console_frame.pack(fill="both", expand=True, padx=20, pady=(10, 20))

        self.console = tk.Text(console_frame, height=12, state="disabled", wrap="word")
        console_scroll = tk.Scrollbar(console_frame, command=self.console.yview)
        self.console.configure(yscrollcommand=console_scroll.set)
        self.console.pack(side="left", fill="both", expand=True)
        console_scroll.pack(side="right", fill="y")

        tk.Button(
            console_frame, text="Clear", command=self.clear_console
        ).pack(side="bottom", anchor="e")

        # Redirect stdout and stderr (stderr catches tracebacks)
        self.console_queue = queue.Queue()
        self._orig_stdout, self._orig_stderr = sys.stdout, sys.stderr
        sys.stdout = TextRedirector(self.console_queue, self._orig_stdout)
        sys.stderr = TextRedirector(self.console_queue, self._orig_stderr)
        self.window.after(100, self.poll_console)

        # ---------- Shared: start GUI ----------

        self.window.mainloop()

    # ==================== Status indicators ====================

    def check_connection(self):
        """Runs every second on the Tk thread. Compares the EMG sample counter with
        the previous check instead of waiting for new samples, so it never blocks the GUI."""

        # Only the counter is read, not the data buffers, so this is cheap
        emg_count = int(self.odh.smm.get_variable("emg_count").item())
        now = time.time()

        # Only an increase counts as new data; a data reset drops the counter to 0
        if self.last_emg_count is not None and emg_count > self.last_emg_count:
            self.last_count_change = now
        self.last_emg_count = emg_count

        streaming = now - self.last_count_change < self.stream_timeout_s
        was_streaming = self.streaming_status.get() == "STREAMING"

        if streaming and not was_streaming:
            self.streaming_status.set("STREAMING")
        elif not streaming and was_streaming:
            # Logged once per dropout, not on every check
            self.streaming_status.set("NOT STREAMING")
            self.create_event("Lost connection to device")
            print(f"No EMG data for {self.stream_timeout_s} s. Check the armband connection.")

        self.update_status_colours()
        self.window.after(1000, self.check_connection)

    # Update the colour of the status indicators: green when active, red otherwise
    def update_status_colours(self):

        def set_colour(cell, label, active):
            colour = "green" if active else "red"
            cell.config(bg=colour)
            label.config(bg=colour, fg="black")

        set_colour(self.recording_cell, self.recording_label, self.recording_status.get() == "RECORDING")
        set_colour(self.streaming_cell, self.streaming_label, self.streaming_status.get() == "STREAMING")

    # ==================== Session info ====================

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
        file_exists = os.path.exists(filepath)

        try:
            if not file_exists:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(self.build_info_header())
                    for comment_line in self.comments:
                        f.write(comment_line + "\n")

                messagebox.showinfo("Saved", f"New session info file created:\n{filepath}")

            else:
                messagebox.showinfo(
                    "Existing file",
                    f"A file with this name already exists.\n"
                    f"New comments will be appended to it:\n{filepath}"
                )

            # Either way, comments added from now on should go to this file
            self.info_filepath = filepath
            self.info_file_label_var.set(f"File: {filename}")

        except OSError as e:
            messagebox.showerror("Error", f"Could not access file:\n{e}")

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

    # ==================== Recording ====================

    def start_recording(self):

        # Only one logging process at a time, otherwise every sample is written twice
        if self.recording_status.get() == "RECORDING":
            print("Already recording. Press Stop recording before starting a new recording.")
            return

        self.create_event("Start recording")           

        self.odh.log_to_file(
            file_path=self.data_folder,
            timestamps=True
        )
        self.recording_status.set("RECORDING")
     

    def stop_recording(self):

        self.odh.stop_all()
        self.create_event("Stop recording")

        self.recording_status.set("NOT RECORDING")

    def reset(self):
        self.create_event("Data reset")
        self.odh.reset()

    # ==================== Live views and data quality ====================

    def start_visualize(self):
        self.odh.visualize(block=False)

    def monitor_data(self):
        self.qa.monitor_data(emg_fs=self.emg_fs)

    def set_QA_baseline(self):
        # Run in a background thread so the countdown doesn't block the GUI
        if getattr(self, "_baseline_running", False):
            return  # ignore double-clicks while calibrating
        self._baseline_running = True

        def worker():
            try:
                self.qa.set_baseline()
            except Exception as e:
                print(f"Calibration failed: {e}")
            finally:
                self._baseline_running = False

        threading.Thread(target=worker, daemon=True).start()

    def analyze_device(self):
        self.odh.analyze_hardware()

    # ==================== Screen guided gesturing ====================

    def start_sgt(self):

        self.reset()

        multiprocessing.Process(
            target=run_sgt,
            args=(self.events_file, self.sgt_args)
        ).start()

    # ==================== Plotting ====================

    def plot_data(self):
        plot_data_ext(self)

    # ==================== Events ====================

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

        # Save immediately, as one write so lines from the SGT process can't interleave with it
        with open(self.events_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    # ==================== Console output ====================

    def poll_console(self):
        """Move queued text into the Text widget (runs on the Tk thread)."""
        try:
            while True:
                text = self.console_queue.get_nowait()
                self.console.configure(state="normal")
                self.console.insert(tk.END, text)
                self.console.see(tk.END)
                self.console.configure(state="disabled")
        except queue.Empty:
            pass
        self.window.after(100, self.poll_console)

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")

    # ==================== Exit ====================

    def exit_program(self):
        self.create_event("Exit program")
        sys.stdout, sys.stderr = self._orig_stdout, self._orig_stderr
        self.window.destroy()

    def confirm_exit(self):
        # Used by the window's close (X) button, so an accidental click doesn't end the session
        if messagebox.askyesno("Exit", "Are you sure you want to close the program?"):
            self.exit_program()
