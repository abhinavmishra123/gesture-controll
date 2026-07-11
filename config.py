"""
Configuration for the Hand Gesture Controller.
All settings, gesture mappings, and constants.
"""

# ──────────────────────────────────────────────
# Camera Settings
# ──────────────────────────────────────────────
CAMERA_INDEX = 0
CAMERA_WIDTH = 640               # Lower resolution for massive performance boost
CAMERA_HEIGHT = 360              # MediaPipe resizes internally anyway, so high res just adds lag

# ──────────────────────────────────────────────
# MediaPipe Hand Tracking
# ──────────────────────────────────────────────
MAX_NUM_HANDS = 1
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.6

# ──────────────────────────────────────────────
# Gesture Timings & Thresholds
# ──────────────────────────────────────────────
ACTIVATION_HOLD_TIME = 2.0       # Hold open hand for 2.0s to activate (prevents accidental wake-up)
GESTURE_HOLD_TIME = 0.3          # Hold gesture for 0.3s to trigger action (Ultra fast response)
GESTURE_COOLDOWN = 0.5           # Cooldown before the SAME gesture can trigger again
CONTINUOUS_COOLDOWN = 0.15       # Cooldown for continuous gestures like volume holding
DEACTIVATION_TIMEOUT = 3.0      # No hand for 3s → deactivate
OVERLAY_DISPLAY_TIME = 2.0      # Show overlay notification for 2s

AMBIDEXTROUS_MODE = True         # If True: Right Hand = Mouse Control, Left Hand = Media Control

# ──────────────────────────────────────────────
# Swipe Detection
# ──────────────────────────────────────────────# Swipe detection parameters
SWIPE_THRESHOLD = 0.15           # Minimum distance (normalized 0-1) for a swipe (Requires less movement)
SWIPE_HISTORY_LENGTH = 20        # Number of frames to keep in history
SWIPE_MAX_TIME_MS = 500          # Swipe must complete within 500mswipe (ms)

# ──────────────────────────────────────────────
# Mouse Control Settings
# ──────────────────────────────────────────────
# 1 Euro Filter Parameters
FILTER_MIN_CUTOFF = 0.2          # Lower = heavier smoothing at slow speeds (kills jitter)
FILTER_BETA = 2.0                # Higher = less smoothing at high speeds (kills lag)

# Advanced Mouse Physics
DEADBAND_RADIUS = 0.5            # Dramatically reduced to prevent 'sticky' or 'staircase' jagged movement
ACCELERATION_THRESHOLD = 15.0    # Speed where input = output. (Pixels per frame)
MOUSE_ACCELERATION_FACTOR = 1.2  # Smoother acceleration curve (feels less erratic)

PINCH_THRESHOLD = 0.4            # Multiplier based on hand size (distance from wrist to knuckle). 0.4 means fingers must be VERY close.
TRACKPAD_SENSITIVITY = 4.0       # Base multiplier for relative mouse movement (increased to offset lower acceleration)

# Tap timings (seconds)
MOUSE_SCROLL_SPEED = 150         # Multiplier for two-finger scroll distance




# ──────────────────────────────────────────────
# Hand Landmark Indices
# ──────────────────────────────────────────────
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20

# ──────────────────────────────────────────────
# Gesture Names
# ──────────────────────────────────────────────
GESTURE_NONE = "NONE"
GESTURE_OPEN_HAND = "OPEN_HAND"
GESTURE_BLADE = "BLADE"
GESTURE_FIST = "FIST"
GESTURE_THUMBS_UP = "THUMBS_UP"
GESTURE_THUMBS_DOWN = "THUMBS_DOWN"
GESTURE_L_SHAPE = "L_SHAPE"
GESTURE_PEACE = "PEACE"
GESTURE_POINTING = "POINTING"
GESTURE_PINCH = "PINCH"
GESTURE_PEN_GRIP = "PEN_GRIP"
GESTURE_PEN_CLICK = "PEN_CLICK"

# ──────────────────────────────────────────────
# Gesture → Keyboard Shortcut Mapping
# ──────────────────────────────────────────────
GESTURE_ACTIONS = {
    GESTURE_FIST: {
        "key": "playpause",
        "label": "⏯  Play / Pause",
        "emoji": "✊",
    },
    GESTURE_THUMBS_UP: {
        "key": "volumeup",
        "label": "🔊  Volume Up",
        "emoji": "👍",
    },
    GESTURE_THUMBS_DOWN: {
        "key": "volumedown",
        "label": "🔉  Volume Down",
        "emoji": "👎",
    },
    GESTURE_PEACE: {
        "key": "volumemute",
        "label": "🔇  Mute / Unmute",
        "emoji": "✌️",
    },
    GESTURE_L_SHAPE: {
        "key": "scroll",
        "label": "↕️  Scroll Mode",
        "emoji": "👆",
    },
}

# Swipe actions (separate because they depend on direction)
SWIPE_ACTIONS = {
    "SWIPE_LEFT": {
        "key": "left",
        "label": "⏪  Seek Backward",
        "emoji": "⏪",
    },
    "SWIPE_RIGHT": {
        "key": "right",
        "label": "⏩  Seek Forward",
        "emoji": "⏩",
    }
}

# ──────────────────────────────────────────────
# App States
# ──────────────────────────────────────────────
STATE_SLEEPING = "SLEEPING"
STATE_ACTIVATING = "ACTIVATING"
STATE_READY = "READY"
STATE_REGISTERING = "REGISTERING"

# ──────────────────────────────────────────────
# Overlay Appearance
# ──────────────────────────────────────────────
OVERLAY_WIDTH = 420
OVERLAY_HEIGHT = 90
OVERLAY_BG = "#1a1a2e"
OVERLAY_FG = "#e2e8f0"
OVERLAY_ACCENT = "#7c3aed"
OVERLAY_SUCCESS = "#10b981"
OVERLAY_WARNING = "#f59e0b"
OVERLAY_DANGER = "#ef4444"
OVERLAY_FONT_FAMILY = "Segoe UI"
OVERLAY_FONT_SIZE_TITLE = 14
OVERLAY_FONT_SIZE_SUB = 11
