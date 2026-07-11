"""
Hand Gesture Controller — Main Entry Point
Standard window application that runs hand gesture tracking in the background
and controls any media player via simulated keyboard shortcuts.

Usage:
    pythonw main.pyw
"""

import os
import sys
import io
import threading
import tkinter as tk
from PIL import Image, ImageDraw
import keyboard

# When running via pythonw.exe, stdout is None which causes print() to crash.
# Redirect output to a log file to prevent crashes and keep debug info.
if sys.stdout is None:
    sys.stdout = open(os.path.join(os.path.dirname(__file__), "gesture.log"), "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = sys.stdout

# Fix Unicode encoding for Windows terminal and force line buffering
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from overlay import Overlay
from hand_tracker import HandTracker
from config import STATE_SLEEPING, STATE_REGISTERING

# ──────────────────────────────────────────────────────
# App Class
# ──────────────────────────────────────────────────────

class GestureControllerApp:
    """Main application — manages overlay and hand tracker."""

    def __init__(self):
        self.overlay = Overlay()
        self.tracker = HandTracker(overlay=self.overlay)
        self._tracking_active = False

    def run(self):
        """Start the application."""
        print("=" * 55)
        print("  [Hand] Gesture Controller")
        print("  Control any media player with hand gestures!")
        print("=" * 55)
        print()
        print("  Starting up...")
        print("  -> App will appear in Taskbar")
        print()

        # Run tkinter overlay on the main thread (required by tkinter)
        root = tk.Tk()
        self.overlay.setup(root)
        
        # Connect GUI buttons to App functions
        self.overlay.set_callbacks(
            on_start=self._start_tracking,
            on_stop=self._stop_tracking,
            on_quit=self._quit
        )

        # Handle window close
        def on_close():
            self._quit()

        root.protocol("WM_DELETE_WINDOW", on_close)

        self._setup_hotkey()

        # Auto-start tracking and minimize to taskbar
        self._start_tracking()
        self.overlay.hide()

        try:
            root.mainloop()
        except KeyboardInterrupt:
            self._quit()

    # ──────────────────────────────────────────────
    # Tracking Control
    # ──────────────────────────────────────────────

    def _setup_hotkey(self):
        """Register the global keyboard shortcuts."""
        try:
            keyboard.add_hotkey('ctrl+alt+s', self._toggle_tracking)
            print("[App] Global hotkey Ctrl+Alt+S registered.")
        except Exception as e:
            print(f"[App] Failed to bind global hotkey: {e}")

    def _toggle_tracking(self):
        """Toggle tracking state via hotkey."""
        if self._tracking_active:
            # We must schedule this on the main thread if it touches tkinter UI
            self.overlay.root.after_idle(self._stop_tracking)
        else:
            self.overlay.root.after_idle(self._start_tracking)

    def _start_tracking(self):
        """Start hand gesture tracking."""
        if not self._tracking_active:
            self._tracking_active = True
            self.tracker.start()
            self.overlay.show()
            self.overlay.set_state(STATE_SLEEPING)
            self.overlay.show_action("\U0001f680", "Tracking Started!")
            print("[App] Tracking started -- show open hand to activate")

    def _stop_tracking(self):
        """Stop hand gesture tracking."""
        if self._tracking_active:
            self._tracking_active = False
            self.tracker.stop()
            self.overlay.set_state(STATE_SLEEPING)
            self.overlay.show_action("\u23f9\ufe0f", "Tracking Stopped")
            self.overlay.hide()
            print("[App] Tracking stopped")

    def _quit(self):
        """Clean shutdown."""
        print("[App] Shutting down...")
        self._stop_tracking()
        self.overlay.destroy()
        os._exit(0)  # Force exit all threads


# ──────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────

if __name__ == "__main__":
    app = GestureControllerApp()
    app.run()
