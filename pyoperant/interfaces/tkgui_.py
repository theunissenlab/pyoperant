import Queue
import glob
import os
import threading
import time

import Tkinter as tk

from pyoperant.interfaces import base_
from pyoperant.interfaces.utils import MessageStatus


class TkInterface(base_.BaseInterface):
    """GUI for switching between automatic and manual stimulus conditions

    Runs a Tk GUI in a separate thread, managing operational state
    through a shared dictionary and communicating through Queues
    """
    def __init__(self, state, *args, **kwargs):
        """Initialize the interface

        Parameters
        ----------
        state
            Mutable dictionary object that is shared between main Pyoperant
            control and the GUI thread
        """
        super(TkInterface, self).__init__(*args, **kwargs)
        self.event_queues = {
            "play": Queue.Queue(),
            "quit": Queue.Queue(),
            "status_msg": Queue.Queue(),
        }
        self.state = state
        self.state.update({
            "condition": "normal",
            "paused": True,
            "stimulus_dir": None,
            "selected_stim": None
        })

    def push(self, key, msg):
        """Put an object onto a specific queue"""
        self.event_queues[key].put(msg)

    def set_status(self, msg):
        """Send an event to update the status text in the GUI"""
        self.push("status_msg", msg)

    def clear_events(self):
        """Clear all event queues except the quit event queueself.

        Use this to clear out accumulated events that can build up
        from multiple clicks or clicks that occur in the middle of trials
        """
        for k, q in self.event_queues.items():
            if k != "quit":
                q.queue.clear()

    def open(self):
        self.window = GUIThread(self.state, self.event_queues)

    def close(self):
        self.window.quit()
        self.window.join()

    def _read_bool(self, key=None):
        return self.state[key]

    def _read(self, timeout=None, key=None):
        return self.state[key]

    def _poll(self, timeout=None, last_value=None, key=None):
        """Poll an event queue and return when message is recieved

        Parameters
        ----------
        timeout
            Time in seconds after which to break out of polling
        key
            Key of queue to read from ("play" or "quit")

        Returns
        -------
        None if the queue is empty after the timeout period,
        or the value of the next item to be pushed onto the queue. Any
        remaining items on the queue are cleared.
        """
        if key == "play":
            self.set_status("Ready (waiting for user)")

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

        Parameters
        ----------
        state
            Mutable dictionary object that is shared between main Pyoperant
            control and the GUI thread
        event_queues
            Dictionary of queue name to Queue.Queue instance, for pushing
            events between threads.
        """
        threading.Thread.__init__(self)
        self.state = state
        self.event_queues = event_queues
        self.known_files = []
        self.countdown = None
        self.root = None
        self.update_labels_after = None

        self.start()

    def quit(self):
        """Push quit message onto all queues and close Tk window

        Pushes MessageStatus.QUIT onto all queues so anyone polling
        for a message will receive a quit signal.
        """
        for key, q in self.event_queues.items():
            q.put(MessageStatus.QUIT)

        self._cancel_countdown()
        if self.update_labels_after is not None:
            self.root.after_cancel(self.update_labels_after)
            self.update_labels_after = None

        if self.root is None:
            return

        self.root.quit()
        self.root = None

    def setup_vars(self):
        self.value = tk.StringVar(value="normal")
        self.paused = tk.BooleanVar(value=True)
        self.pause_button_text = tk.StringVar(value="Run Experiment")
        self.next_stim_label_text = tk.StringVar(value="No stim found")
        self.status_label_text = tk.StringVar(value="Paused in {} mode.".format(self.value.get()))

    def setup(self):
        top_frame = tk.Frame(self.root)
        bottom_frame = tk.Frame(self.root)
        left_frame = tk.Frame(bottom_frame)
        right_frame = tk.Frame(bottom_frame, bg="black")

        status_frame = tk.Frame(top_frame)
        select_condition_frame = tk.Frame(top_frame)
        stim_control_frame = tk.Frame(right_frame)
        stim_select_frame = tk.Frame(left_frame)

        tk.Label(status_frame, text="Status: ").pack(side="left")
        status_label = tk.Label(status_frame, textvariable=self.status_label_text)

        status_label.pack(side="left")

        self.idle_button = tk.Button(
            stim_control_frame,
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

        normal_button.pack(side="left", expand=False)
        online_button.pack(side="left", expand=False)


        self.play_button = tk.Button(
            stim_control_frame,
            text="Play Stimulus",
            command=self.on_play,
            default="active"
        )

        self.stim_label = tk.Label(stim_control_frame, textvariable=self.next_stim_label_text)
        self.stim_listbox = tk.Listbox(stim_select_frame, selectmode=tk.SINGLE)
        self.stim_listbox.config(width=0)
        self.stim_listbox.bind('<<ListboxSelect>>', self.on_stim_select)

        top_frame.grid(row=0, column=0, padx=10, ipadx=30)
        bottom_frame.grid(row=1, column=0)
        left_frame.grid(row=0, column=0, padx=5, pady=5)
        right_frame.grid(row=0, column=1, padx=5, pady=5)

        status_frame.grid(row=0, column=0, padx=20, pady=2)
        select_condition_frame.grid(row=1, column=0, padx=5, pady=5)
        stim_control_frame.pack(fill="both", expand=False)
        stim_select_frame.pack(fill="both", expand=False)
        self.value.trace("w", self.on_condition_change)
        self.idle_button.pack(expand=False, ipadx=20)
        self.play_button.pack(expand=False, padx=40)
        self.stim_label.pack(expand=False)
        self.stim_listbox.pack(expand=False)
        self.play_button.config(state="disabled")
        self.stim_listbox.config(state="disabled")
        right_frame.grid_propagate(0)

    def _set_state(self, v):
        """Change the current condition between ("normal" and "online") mode

        It sends an abort signal to all queues so polling listeners
        can know to abort what they were waiting for, and if the value
        is changed, sets the new state and pauses the system.
        """
        self.abort_all_queues()
        if v != self.value.get():
            self.value.set(v)
            self._toggle_pause(True)

    def _toggle_pause(self, paused=None):
        """Switch pause between True and False

        When the system transitions between pause states,
        sends a MessageStatus.ABORT signal to all waiting listeners
        """
        if paused is None:
            self.paused.set(not self.paused.get())
        else:
            self.paused.set(paused)

        self.abort_all_queues()
        self.state["paused"] = self.paused.get()
        if self.paused.get():
            self.pause_button_text.set("Resume experiment")
            self.status_label_text.set("Pausing after this trial...")
            self._cancel_countdown()
        else:
            self.pause_button_text.set("Pause experiment")

    def on_condition_change(self, *args, **kwargs):
        """Switch condition between normal playbacks and online playbacks"""
        self.state["condition"] = self.value.get()
        if not self.state["paused"]:
            self._cancel_countdown()
            self.status_label_text.set(
                "Changing to {} condition after this trial...".format(self.value.get())
            )

        # Enable / disable irrelevant buttons to the current condition
        if self.state["condition"] == "online":
            self._toggle_pause(False)
            self.play_button.config(state="normal")
            self.stim_listbox.config(state="normal")
            self.idle_button.config(state="disabled")

        elif self.state["condition"] == "normal":
            self._toggle_pause(True)
            self.play_button.config(state="disabled")
            self.stim_listbox.config(state="disabled")
            self.idle_button.config(state="normal")

    def on_play(self):
        """Handler for play button clicked"""
        if self.state["paused"]:
            self.status_label_text.set("Resume experiment to play stimuli")
        self.event_queues["play"].put(MessageStatus.NORMAL)

    def abort_all_queues(self):
        """Push an abort message to all waiting listeners"""
        for k, q in self.event_queues.items():
            q.put(MessageStatus.ABORT)

    def on_stim_select(self, event):
        """Update state to reflect newly selected stimulus to play"""
        listbox = event.widget
        if not listbox.curselection():
            full_path = None
        else:
            index = int(listbox.curselection()[0])
            full_path = self.stim_mapping[index]
        self.state["selected_stim"] = full_path
        self.update_queued_label(full_path)

    def update_queued_label(self, stim_path):
        """Update the label showing the next stim to be played"""
        if self.state["condition"] == "normal":
            self.next_stim_label_text.set("Sampling from stim directory")
        else:
            file_name = os.path.splitext(os.path.basename(stim_path))[0]
            self.next_stim_label_text.set("Queued\n{}".format(file_name))

    def _update_labels(self):
        """Periodic callback to update labels without a specific trigger

        Repeats every 0.5 secondsself.

        Checks stimulus dir to see if new stimuli have been added.
        Updates the status message if any other threads have requested
        to change the message.
        """
        files = glob.glob(os.path.join(self.state["stimulus_dir"], "*.wav"))

        files = sorted(files, key=os.path.getmtime, reverse=True)
        if set(files) != set(self.known_files):
            self.stim_mapping = {}
            self.known_files = files
            self.stim_listbox.config(state="normal")
            self.stim_listbox.delete(0, tk.END)
            for i, file in enumerate(files):
                self.stim_listbox.insert(
                    i, " ".join([
                        os.path.basename(file),
                        time.strftime('(%H:%M %m/%d/%y)', time.gmtime(os.path.getmtime(file)))]
                    )
                )
                self.stim_mapping[i] = file
            self.stim_listbox.config(state="disabled")

        if self.state["selected_stim"] is not None:
            full_path = self.state["selected_stim"]
        else:
            full_path = max(files, key=os.path.getmtime)
        self.update_queued_label(full_path)

        for msg in list(self.event_queues["status_msg"].queue):
            if isinstance(msg, basestring):
                self.status_label_text.set(msg)
            elif isinstance(msg, dict) and "iti" in msg and self.state["condition"] == "normal":
                self._countdown(msg["iti"])
        self.event_queues["status_msg"].queue.clear()

        self.update_labels_after = self.root.after(500, self._update_labels)

    def _countdown(self, t):
        """Present a countdown status message that updates every second"""
        if t < 0 or self.state["condition"] == "online":
            self.countdown = None
            return
        self.status_label_text.set("Next trial in {:.0f}s".format(t))
        self.countdown = self.root.after(1000, lambda: self._countdown(t - 1))

    def _cancel_countdown(self):
        """Interrupts the current countdown"""
        if self.countdown is not None:
            self.root.after_cancel(self.countdown)
            self.countdown = None

    def run(self):
        self.root = tk.Tk()

        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.title("Pyoperant Playback Stimulus Controller")

        self.setup_vars()
        self.setup()

        self.update_labels_after = self.root.after(500, self._update_labels)

        # Center window
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws / 2) - (w / 2)
        y = (hs / 2) - (h / 2)
        self.root.geometry('+%d+%d' % (x, y))

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()
