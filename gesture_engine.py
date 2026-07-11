"""
Gesture Recognition Engine
Classifies hand landmarks into named gestures with debouncing and swipe detection.
"""

import time
import math
from config import (
    THUMB_TIP, THUMB_MCP, THUMB_IP,
    INDEX_TIP, INDEX_PIP, INDEX_MCP,
    MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP,
    RING_TIP, RING_PIP,
    PINKY_TIP, PINKY_PIP, PINKY_MCP,
    WRIST,
    GESTURE_NONE, GESTURE_OPEN_HAND, GESTURE_FIST,
    GESTURE_THUMBS_UP, GESTURE_THUMBS_DOWN,
    GESTURE_L_SHAPE, GESTURE_PEACE, GESTURE_POINTING, GESTURE_PINCH,
    GESTURE_HOLD_TIME, GESTURE_COOLDOWN, CONTINUOUS_COOLDOWN,
    SWIPE_THRESHOLD, SWIPE_HISTORY_LENGTH, SWIPE_MAX_TIME_MS,
    PINCH_THRESHOLD, AMBIDEXTROUS_MODE,
)


class GestureEngine:
    """Detects and classifies hand gestures from MediaPipe landmarks."""

    def __init__(self):
        # Debouncing state
        self._current_gesture = GESTURE_NONE
        self._gesture_start_time = 0.0
        self._gesture_confirmed = False
        self._last_action_time = {}  # gesture_name → last trigger timestamp
        self._global_last_action_time = 0.0  # Prevents gesture overlap/concurrency
        self._is_clicking_raw = False  # Instant hysteresis state

        # Swipe tracking
        self._position_history = []  # [{x, y, t}, ...]
        self._last_swipe_time = 0.0

    # ──────────────────────────────────────────
    # Finger State Detection
    # ──────────────────────────────────────────

    @staticmethod
    def _distance(p1, p2):
        """Calculate true 3D Euclidean distance between two landmarks."""
        return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (getattr(p1, 'z', 0) - getattr(p2, 'z', 0))**2)

    def _is_finger_extended(self, landmarks, tip_idx, pip_idx):
        """
        Check if a finger is extended using distance from the wrist.
        This is rotation-independent, so it works even if the hand is tilted!
        When extended, the fingertip is further from the wrist than the PIP joint.
        When curled (fist), the fingertip is pulled closer to the wrist.
        """
        wrist = landmarks[WRIST]
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        
        # A finger is open if its tip is further from the wrist than its middle joint
        return self._distance(tip, wrist) > self._distance(pip, wrist)

    def _is_thumb_extended(self, landmarks, handedness):
        """
        Check if thumb is extended using distance.
        The thumb is extended if its tip is significantly further from the
        pinky base (MCP) than its own base (CMC/MCP).
        """
        tip = landmarks[THUMB_TIP]
        mcp = landmarks[THUMB_MCP]
        wrist = landmarks[WRIST]
        pinky_mcp = landmarks[PINKY_MCP]
        
        # When thumb is open/extended, it moves far away from the pinky base
        # When closed (fist), it tucks in close to the palm/pinky
        return self._distance(tip, pinky_mcp) > self._distance(mcp, pinky_mcp) * 1.2

    def _get_finger_states(self, landmarks, handedness):
        """
        Returns a dict of finger names → True/False (extended or not).
        """
        return {
            "thumb": self._is_thumb_extended(landmarks, handedness),
            "index": self._is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP),
            "middle": self._is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP),
            "ring": self._is_finger_extended(landmarks, RING_TIP, RING_PIP),
            "pinky": self._is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP),
        }

    def _count_fingers(self, finger_states):
        """Count number of extended fingers."""
        return sum(1 for v in finger_states.values() if v)

    # ──────────────────────────────────────────
    # Gesture Classification
    # ──────────────────────────────────────────

    def _classify_gesture(self, landmarks, handedness):
        """
        Classify the current hand pose into a named gesture.
        Returns one of the GESTURE_* constants.
        """
        fingers = self._get_finger_states(landmarks, handedness)
        thumb = fingers["thumb"]
        index = fingers["index"]
        middle = fingers["middle"]
        ring = fingers["ring"]
        pinky = fingers["pinky"]

        count = self._count_fingers(fingers)
        
        # Calculate dynamic hand size to make the threshold relative (immune to distance from camera!)
        wrist = landmarks[WRIST]
        index_mcp = landmarks[INDEX_MCP]
        hand_size = self._distance(wrist, index_mcp)
        base_threshold = hand_size * PINCH_THRESHOLD

        # ✋ Open hand — 4 main fingers extended
        if index and middle and ring and pinky:
            return GESTURE_OPEN_HAND

        # ✊ Fist — no fingers extended
        if count == 0:
            return GESTURE_FIST

        # 👍 Thumbs up — only thumb extended, thumb tip ABOVE wrist
        if thumb and not index and not middle and not ring and not pinky:
            wrist_y = landmarks[WRIST].y
            thumb_tip_y = landmarks[THUMB_TIP].y
            if thumb_tip_y < wrist_y:
                return GESTURE_THUMBS_UP
            else:
                return GESTURE_THUMBS_DOWN

        # ✌️ Peace — index + middle extended, others closed
        if not thumb and index and middle and not ring and not pinky:
            return GESTURE_PEACE

        # ☝️ Pointing (Mouse Move!) — only index extended
        if not thumb and index and not middle and not ring and not pinky:
            return GESTURE_POINTING

        # ☝️ L-Shape (Scroll!) — index out, thumb extended, others closed
        if index and thumb and not middle and not ring and not pinky:
            return GESTURE_L_SHAPE

        return GESTURE_NONE

    # ──────────────────────────────────────────
    # Swipe Detection
    # ──────────────────────────────────────────

    def _detect_swipe(self, landmarks):
        """
        Track wrist position over time and detect horizontal swipes.
        Returns 'SWIPE_LEFT', 'SWIPE_RIGHT', or None.
        """
        now = time.time() * 1000  # ms
        # Track the fingertip instead of the wrist! 
        # When you 'slap' or wave, the wrist is the pivot and barely moves, but the fingertips travel far.
        anchor = landmarks[MIDDLE_TIP]

        self._position_history.append({
            "x": anchor.x,
            "y": anchor.y,
            "t": now,
        })

        # Keep only history within the time window
        self._position_history = [p for p in self._position_history if now - p["t"] <= SWIPE_MAX_TIME_MS]
        
        # Prevent memory leaks just in case
        if len(self._position_history) > 50:
            self._position_history.pop(0)

        if len(self._position_history) < 2:
            return None

        oldest = self._position_history[0]
        newest = self._position_history[-1]
        
        dx = newest["x"] - oldest["x"]
        dy = newest["y"] - oldest["y"]
        dt = newest["t"] - oldest["t"]
        
        if dt <= 0:
            return None

        # Check for significant horizontal movement
        if abs(dx) > SWIPE_THRESHOLD and abs(dx) > abs(dy) * 1.5:
            # Cooldown check for swipes
            if now - self._last_swipe_time < GESTURE_COOLDOWN * 1000:
                return None
            self._last_swipe_time = now
            self._position_history.clear()
            # In a mirrored webcam, dx > 0 means the user moved their hand to their physical RIGHT
            return "SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT"

        return None

    # ──────────────────────────────────────────
    # Main Processing (called every frame)
    # ──────────────────────────────────────────

    def process(self, landmarks, handedness):
        """
        Process a frame's landmarks and return the confirmed gesture + any swipe.

        Args:
            landmarks: MediaPipe hand landmarks (list of 21 landmark objects)
            handedness: "Left" or "Right" string

        Returns:
            dict with:
                "gesture": confirmed gesture name (or GESTURE_NONE)
                "raw_gesture": unconfirmed/current gesture (for UI display)
                "swipe": "SWIPE_LEFT", "SWIPE_RIGHT", or None
                "triggered": True if a NEW action should be triggered this frame
        """
        now = time.time()
        raw_gesture = self._classify_gesture(landmarks, handedness)
        self._is_clicking_raw = (raw_gesture == GESTURE_FIST)
        
        # ── Ambidextrous Mode (Hand Separation) ──
        if AMBIDEXTROUS_MODE and raw_gesture != GESTURE_OPEN_HAND and raw_gesture != GESTURE_NONE:
            # MediaPipe's "Left" is the physical right hand when mirrored
            is_physical_right_hand = (handedness == "Left")
            
            # GESTURE_FIST is overloaded: Click for right hand, Play/Pause for left hand
            is_mouse_specific = raw_gesture in (GESTURE_L_SHAPE, GESTURE_POINTING)
            
            if is_physical_right_hand and raw_gesture not in (GESTURE_L_SHAPE, GESTURE_POINTING, GESTURE_FIST):
                raw_gesture = GESTURE_NONE  # Right hand can only do mouse stuff
            elif not is_physical_right_hand and is_mouse_specific:
                raw_gesture = GESTURE_NONE  # Left hand can only do media stuff
                
        # ── Mouse Anchor Point ──
        # Anchor to the Wrist (WRIST) instead of knuckles or fingertips.
        # This completely isolates the cursor from any finger wiggling or clicking!
        anchor_point = landmarks[WRIST]
        pointer_x, pointer_y = anchor_point.x, anchor_point.y

        # Check for swipe ONLY when hand is OPEN (or NONE, to tolerate motion blur)! 
        # This prevents accidental swipes when just moving an open hand around.
        swipe = None
        if raw_gesture in (GESTURE_OPEN_HAND, GESTURE_NONE):
            swipe = self._detect_swipe(landmarks)
        else:
            # Reset swipe history when explicitly making other gestures (like FIST, POINTING)
            self._position_history.clear()

        # ── Debouncing Logic ──
        triggered = False

        if raw_gesture != self._current_gesture:
            # Gesture changed — start new timer
            self._current_gesture = raw_gesture
            self._gesture_start_time = now
            self._gesture_confirmed = False
        elif not self._gesture_confirmed:
            # Same gesture held — check if held long enough
            hold_time = GESTURE_HOLD_TIME
            if raw_gesture == GESTURE_OPEN_HAND:
                # Open hand needs no hold time for activation feedback
                hold_time = GESTURE_HOLD_TIME



            if now - self._gesture_start_time >= hold_time:
                self._gesture_confirmed = True

                # If user shows an OPEN_HAND, instantly reset all cooldowns!
                # This acts as an "alert" or "reset" gesture so they don't have to hide their hand.
                if raw_gesture == GESTURE_OPEN_HAND:
                    self._last_action_time.clear()
                    self._global_last_action_time = 0.0

                # Check cooldown (use continuous fast cooldown for volume)
                last_time = self._last_action_time.get(raw_gesture, 0)
                cooldown = CONTINUOUS_COOLDOWN if raw_gesture in (GESTURE_THUMBS_UP, GESTURE_THUMBS_DOWN) else GESTURE_COOLDOWN
                
                # Global cooldown prevents overlapping gestures from firing instantly when switching
                if (now - last_time >= cooldown) and (now - self._global_last_action_time >= cooldown):
                    triggered = True
                    self._last_action_time[raw_gesture] = now
                    self._global_last_action_time = now

        return {
            "gesture": self._current_gesture if self._gesture_confirmed else GESTURE_NONE,
            "raw_gesture": raw_gesture,
            "swipe": swipe,
            "triggered": triggered,
            "pointer_x": pointer_x,
            "pointer_y": pointer_y,
            "is_clicking_raw": self._is_clicking_raw,
        }

    def reset(self):
        """Reset all state (e.g., when tracking stops)."""
        self._current_gesture = GESTURE_NONE
        self._gesture_start_time = 0.0
        self._gesture_confirmed = False
        self._last_action_time.clear()
        self._global_last_action_time = 0.0
        self._position_history.clear()
        self._last_swipe_time = 0.0
        self._is_clicking_raw = False
