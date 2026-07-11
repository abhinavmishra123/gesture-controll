"""
Control Panel GUI
A movable, compact sidebar window that lets the user start/stop the camera manually
and displays live gesture feedback along with the embedded camera feed.
"""

import tkinter as tk
from tkinter import ttk
import time
import cv2
from PIL import Image, ImageTk
from config import (
    STATE_SLEEPING, STATE_ACTIVATING, STATE_READY,
    OVERLAY_BG, OVERLAY_FG, OVERLAY_ACCENT,
    OVERLAY_SUCCESS, OVERLAY_WARNING, OVERLAY_FONT_FAMILY
)

class Overlay:
    """Manages the interactive Control Panel window."""

    def __init__(self):
        self.root = None
        self._state = STATE_SLEEPING
        self._action_emoji = "💤"
        self._action_label = "Waiting..."
        self._last_update = 0.0

        # Callbacks
        self.on_start = None
        self.on_stop = None
        self.on_quit = None
        
        # Dragging state
        self._current_x = -1
        self._current_y = -1

    def set_callbacks(self, on_start, on_stop, on_preview=None, on_quit=None):
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_quit = on_quit

    def setup(self, root):
        self.root = root
        
        # Make it a standard window
        self.root.title("Gesture Control")
        
        self.root.configure(bg=OVERLAY_BG)
        self.root.attributes("-alpha", 0.95)

        # UI State
        self.is_collapsed = False

        # Position on the right side of the screen
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        
        # Increased size to fit video (16:9 ratio for video: 256x144)
        self.full_w = 280
        self.full_h = 360
        self.col_w = 60
        self.col_h = 40
        
        self._current_x = self.screen_w - self.full_w - 20
        self._current_y = (self.screen_h // 2) - (self.full_h // 2)
        
        self.root.geometry(self._get_geometry(self.full_w, self.full_h))

        # Custom Styling
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=(OVERLAY_FONT_FAMILY, 10, "bold"), padding=5)
        
        # ── UI Elements ──
        
        # We now use the standard OS window title bar.

        # Video Canvas
        self.frame_video = tk.Frame(self.root, bg="black", bd=2, relief="sunken")
        self.frame_video.pack(fill="x", padx=10, pady=(10, 5))
        
        self.lbl_video = tk.Label(self.frame_video, bg="black", text="Camera Offline", fg="white")
        self.lbl_video.pack(expand=True, fill="both")

        # Status indicator
        self.lbl_status = tk.Label(
            self.root, text="Status: Sleeping", 
            font=(OVERLAY_FONT_FAMILY, 10),
            bg=OVERLAY_BG, fg=OVERLAY_FG
        )
        self.lbl_status.pack(pady=2)

        # Action Feedback Box
        self.frame_action = tk.Frame(self.root, bg="#2a2a4e", bd=2, relief="groove")
        self.frame_action.pack(fill="x", padx=10, pady=5)
        
        self.lbl_action = tk.Label(
            self.frame_action, text="💤 Waiting...",
            font=(OVERLAY_FONT_FAMILY, 12, "bold"),
            bg="#2a2a4e", fg=OVERLAY_FG, height=2
        )
        self.lbl_action.pack(expand=True)

        # Buttons
        self.frame_btns = tk.Frame(self.root, bg=OVERLAY_BG)
        self.frame_btns.pack(pady=5)

        self.btn_toggle = ttk.Button(self.frame_btns, text="Stop Tracking", command=self._toggle_tracking)
        self.btn_toggle.grid(row=0, column=0, padx=5)

        self.btn_quit = ttk.Button(self.frame_btns, text="Quit App", command=self._trigger_quit)
        self.btn_quit.grid(row=0, column=1, padx=5)

        # No need for collapsed button since the user can just minimize the window natively


        # Render loop for timing-based resets
        self._render()

    def hide(self):
        if self.root:
            self.root.iconify()
            
    def show(self):
        if self.root:
            self.root.deiconify()

    def _get_geometry(self, w, h):
        return f"{w}x{h}+{self._current_x}+{self._current_y}"



    # ── Button Handlers ──
    

    
    def _toggle_tracking(self):
        if self.btn_toggle["text"] == "Stop Tracking":
            self.btn_toggle.config(text="Start Tracking")
            if self.on_stop: self.on_stop()
        else:
            self.btn_toggle.config(text="Stop Tracking")
            if self.on_start: self.on_start()

    def _trigger_quit(self):
        if self.on_quit: self.on_quit()

    # ── Update Methods (Thread-Safe) ──

    def update_frame(self, cv2_frame):
        """Called by background thread to push a video frame to the GUI."""
        if self.is_collapsed or not self.root:
            return  # CPU Saver: Don't process video if GUI is hidden!
            
        now = time.time()
        # CPU Saver: Cap video render framerate to ~15 FPS
        if not hasattr(self, '_last_frame_time'):
            self._last_frame_time = 0
        if now - self._last_frame_time < 0.06:
            return
        self._last_frame_time = now

        try:
            rgb = cv2.cvtColor(cv2_frame, cv2.COLOR_BGR2RGB)
            # Resize to fit the label (256x144 is 16:9)
            img = Image.fromarray(rgb).resize((256, 144))
            photo = ImageTk.PhotoImage(image=img)
            self.root.after(0, lambda p=photo: self._set_image(p))
        except Exception:
            pass
            
    def _set_image(self, photo):
        self.lbl_video.config(image=photo, text="")
        self.lbl_video.image = photo

    def set_state(self, state):
        self._state = state
        if not self.root: return
        
        color = OVERLAY_SUCCESS if state == STATE_READY else OVERLAY_WARNING if state == STATE_ACTIVATING else OVERLAY_FG
        text = f"Status: {state.capitalize()}"
        
        self.root.after(0, lambda: self.lbl_status.config(text=text, fg=color))

    def show_action(self, emoji, label):
        self._action_emoji = emoji
        self._action_label = label
        self._last_update = time.time()
        
        if not self.root: return
        text = f"{emoji} {label}"
        self.root.after(0, lambda: self.lbl_action.config(text=text, fg=OVERLAY_SUCCESS))

    def _render(self):
        """Reset action text after a delay."""
        now = time.time()
        if now - self._last_update > 2.0 and self._action_label != "Waiting...":
            self._action_emoji = "💤"
            self._action_label = "Waiting..."
            self.lbl_action.config(text="💤 Waiting...", fg=OVERLAY_FG)

        if self.root:
            self.root.after(100, self._render)

    def destroy(self):
        if self.root:
            self.root.quit()
