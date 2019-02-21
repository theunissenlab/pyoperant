import Tkinter as tk
import threading
import glob
import os

import Queue

from pyoperant.interfaces import base_
from pyoperant.interfaces.utils import MessageStatus


class TkInterface(base_.BaseInterface):
    def __init__(self, state, *args, **kwargs):
        super(TkInterface, self).__init__(*args, **kwargs)
        self.event_queues = {
            "play": Queue.Queue(),
            "quit": Queue.Queue(),
            "dummy": Queue.Queue(),
            "status_msg": Queue.Queue(),
        }
        self.state = state
        self.state.update({
            "condition": "normal",
            "paused": True,
            "stimulus_dir": None
        })

        self.open()

    def push(self, key, msg):
        self.event_queues[key].put(msg)

    def set_status(self, msg):
        self.push("status_msg", msg)

    def clear_events(self):
        """Clear all event queues except the quit event queueself.

        Use this to clear out accumulated events.
        """
        for k, q in self.event_queues.items():
            if k != "quit":
                q.queue.clear()

    def open(self):
        self.window = GUIThread(self.state, self.event_queues)

    def _read_bool(self, key=None):
        return self.state[key]

    def _read(self, timeout=None, key=None):
        return self.state[key]

    def _write(self, value, key=None, **kwargs):
        """Write to GUI panels"""
        self.push(key, value)

    def _poll(self, timeout=None, last_value=None, key=None):
        if key == "play":
            self.set_status("Ready")

        try:
            val = self.event_queues[key].get(timeout=timeout)
        except Queue.Empty:
            return None
        else:
            self.event_queues[key].queue.clear()
            return val


class GUIThread(threading.Thread):

    def __init__(self, state, event_queues):
        """Thread to run GUI

        Args
        ====
        - state (dict)
        - event_queues (dict)
        """
        threading.Thread.__init__(self)
        self.state = state
        self.event_queues = event_queues
        self.start()

    def quit(self):
        for key, q in self.event_queues.items():
            q.put(MessageStatus.QUIT)
        self.root.quit()

    def setup_vars(self):
        self.value = tk.StringVar(value="normal")
        self.paused = tk.BooleanVar(value=True)
        self.pause_button_text = tk.StringVar(value="Run")
        self.next_stim_label_text = tk.StringVar(value="No stim found")
        self.status_label_text = tk.StringVar(value="Paused in {} mode.".format(self.value.get())

    def setup(self):
        status_frame = tk.Frame(self.root)
        select_condition_frame = tk.Frame(self.root)
        stim_control_frame = tk.Frame(self.root)

        tk.Label(status_frame, text="Status: ").pack(side="left")
        status_label = tk.Label(status_frame, textvariable=self.status_label_text)

        status_label.pack(side="left")

        idle_button = tk.Button(
            select_condition_frame,
            textvariable=self.pause_button_text,
            command=self._toggle_pause,
        )

        normal_button = tk.Radiobutton(
            select_condition_frame,
            text="Normal (autoplay) mode",
            command=lambda: self._set_state("normal"),
            variable=self.value,
            value="normal",
        )

        online_button = tk.Radiobutton(
            select_condition_frame,
            text="Online (manual) mode",
            command=lambda: self._set_state("online"),
            variable=self.value,
            value="online",
        )

        idle_button.pack(side="left", fill=tk.X)
        normal_button.pack(side="left")
        online_button.pack(side="left")

        self.play_button = tk.Button(
            stim_control_frame,
            text="Play Stimulus",
            command=self.on_play,
            default="active"
        )

        self.stim_label = tk.Label(stim_control_frame, textvariable=self.next_stim_label_text)

        status_frame.grid(row=0, column=0, padx=10, pady=10)
        select_condition_frame.grid(row=1, column=0, padx=10, pady=10)
        stim_control_frame.grid(row=2, column=0, padx=10, pady=10)

        self.value.trace("w", self.on_condition_change)
        self.paused.trace("w", self.on_pause_toggle)

    def _set_state(self, v):
        self.abort_all_queues()
        if v != self.value.get():
            self.value.set(v)
            self._toggle_pause(True)

    def _toggle_pause(self, paused=None):
        if paused is None:
            self.paused.set(not self.paused.get())
        else:
            self.paused.set(paused)

        self.abort_all_queues()
        self.state["paused"] = self.paused.get()
        if self.paused.get():
            self.pause_button_text.set("Resume")
            self.status_label_text.set("Pausing after this trial...")
        else:
            self.pause_button_text.set("Pause")

    def on_condition_change(self, *args, **kwargs):
        self.state["condition"] = self.value.get()
        if not self.state["paused"]:
            self.status_label_text.set(
                "Changing to {} condition after this trial...".format(self.value.get())
            )
        else:
            self.status_label_text.set(
                "Paused in {} mode.".format(self.value.get())
            )

        if self.state["condition"] == "online":
            self.stim_label.pack()
            self.play_button.pack()
        elif self.state["condition"] == "normal":
            self.play_button.pack_forget()
            self.stim_label.pack_forget()

    def on_play(self):
        self.event_queues["play"].put(MessageStatus.NORMAL)

    def abort_all_queues(self):
        for k, q in self.event_queues.items():
            q.put(MessageStatus.ABORT)

    def _update_labels(self):
        files = glob.glob(os.path.join(self.state["stimulus_dir"], "*.wav"))
        latest_file = max(files, key=os.path.getmtime)
        file_location = os.path.join(
            os.path.basename(os.path.dirname(latest_file)),
            os.path.basename(latest_file)
        )
        self.next_stim_label_text.set("Playing {}".format(file_location))

        for msg in list(self.event_queues["status_msg"].queue):
            if isinstance(msg, basestring):
                self.status_label_text.set(msg)
            elif isinstance(msg, dict) and "iti" in msg and self.state["condition"] == "normal":
                self._countdown(msg["iti"])
        self.event_queues["status_msg"].queue.clear()
        self.root.after(500, self._update_labels)

    def _countdown(self, t):
        if t < 0 or self.state["condition"] == "online":
            return
        self.status_label_text.set("Next trial in {:.0f}s".format(t))
        self.root.after(1000, lambda: self._countdown(t - 1))

    def run(self):
        self.root = tk.Tk()
        # self.root.geometry("500x500")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.title("Stimulus Controller")

        self.setup_vars()
        self.setup()

        self.root.after(500, self._update_labels)
        # self.root.eval('tk::PlaceWindow %s center' % w.winfo_pathname(w.winfo_id()))

        self.root.mainloop()
