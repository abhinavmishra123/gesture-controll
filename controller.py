"""
Keyboard Controller
Simulates system-wide keyboard shortcuts based on detected gestures.
Uses direct Windows OS calls for zero latency.
"""

import ctypes
from config import GESTURE_ACTIONS, SWIPE_ACTIONS

# Windows Virtual-Key Codes for Media and Navigation
VK_MAPPING = {
    "playpause": 0xB3,
    "nexttrack": 0xB0,
    "prevtrack": 0xB1,
    "volumemute": 0xAD,
    "volumedown": 0xAE,
    "volumeup": 0xAF,
    "right": 0x27,
    "left": 0x25,
}

def _press_key(key_name, presses=1):
    vk_code = VK_MAPPING.get(key_name)
    if not vk_code:
        print(f"[Controller] Unknown key: {key_name}")
        return
        
    for _ in range(presses):
        # 0x0001 is KEYEVENTF_EXTENDEDKEY, 0x0002 is KEYEVENTF_KEYUP
        ctypes.windll.user32.keybd_event(vk_code, 0, 0x0001, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 0x0001 | 0x0002, 0)


class Controller:
    """Maps gestures to keyboard shortcuts and executes them."""

    def __init__(self):
        self._action_log = []  # Recent actions for debugging

    def execute_gesture(self, gesture_name):
        """
        Execute the keyboard shortcut mapped to a gesture.

        Args:
            gesture_name: One of the GESTURE_* constants from config.

        Returns:
            dict with 'key', 'label', 'emoji' if action was executed, None otherwise.
        """
        action = GESTURE_ACTIONS.get(gesture_name)
        if action:
            try:
                # Volume keys need to be pressed multiple times to be noticeable
                if action["key"] in ("volumeup", "volumedown"):
                    _press_key(action["key"], presses=2)
                else:
                    _press_key(action["key"])
                    
                self._action_log.append({
                    "gesture": gesture_name,
                    "key": action["key"],
                    "label": action["label"],
                })
                # Keep log manageable
                if len(self._action_log) > 100:
                    self._action_log = self._action_log[-50:]
                return action
            except Exception as e:
                print(f"[Controller] Error pressing key '{action['key']}': {e}")
                return None
        return None

    def execute_swipe(self, swipe_direction):
        """
        Execute the keyboard shortcut for a swipe gesture.

        Args:
            swipe_direction: 'SWIPE_LEFT' or 'SWIPE_RIGHT'

        Returns:
            dict with 'key', 'label', 'emoji' if action was executed, None otherwise.
        """
        action = SWIPE_ACTIONS.get(swipe_direction)
        if action:
            try:
                _press_key(action["key"])
                self._action_log.append({
                    "gesture": swipe_direction,
                    "key": action["key"],
                    "label": action["label"],
                })
                if len(self._action_log) > 100:
                    self._action_log = self._action_log[-50:]
                return action
            except Exception as e:
                print(f"[Controller] Error pressing key '{action['key']}': {e}")
                return None
        return None

    def get_recent_actions(self, count=5):
        """Get the most recent actions for debugging/display."""
        return self._action_log[-count:]

