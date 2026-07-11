"""
Hand Tracker
Handles webcam capture, MediaPipe hand landmark detection,
and coordinates gesture recognition + controller actions.
Runs in a background thread.

Uses the modern MediaPipe Tasks Vision API (not the legacy mp.solutions).
"""

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
import time
import threading
import os
import sys
import io
import urllib.request

# Fix Unicode encoding for Windows terminal and force line buffering
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from config import (
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
    MAX_NUM_HANDS, MIN_DETECTION_CONFIDENCE, MIN_TRACKING_CONFIDENCE,
    GESTURE_OPEN_HAND, GESTURE_NONE, GESTURE_L_SHAPE,
    GESTURE_POINTING, GESTURE_FIST,
    GESTURE_ACTIONS,
    STATE_SLEEPING, STATE_ACTIVATING, STATE_READY, STATE_REGISTERING,
    ACTIVATION_HOLD_TIME, DEACTIVATION_TIMEOUT,
    AMBIDEXTROUS_MODE
)
from gesture_engine import GestureEngine
from controller import Controller
from mouse_controller import MouseController
from biometrics import HandBiometrics


# ──────────────────────────────────────────────
# Hand skeleton connections for drawing
# ──────────────────────────────────────────────
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),                     # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),                     # Index
    (5, 9), (9, 10), (10, 11), (11, 12),                 # Middle
    (9, 13), (13, 14), (14, 15), (15, 16),               # Ring
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),     # Pinky + palm
]

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_FILENAME = "hand_landmarker.task"


def download_model(dest_path):
    """Download the hand landmarker model if not already present."""
    if os.path.exists(dest_path):
        return dest_path
    print(f"[HandTracker] Downloading hand landmarker model...")
    print(f"  From: {MODEL_URL}")
    print(f"  To:   {dest_path}")
    try:
        urllib.request.urlretrieve(MODEL_URL, dest_path)
        print(f"[HandTracker] Model downloaded successfully ({os.path.getsize(dest_path) / 1e6:.1f} MB)")
    except Exception as e:
        print(f"[HandTracker] ERROR downloading model: {e}")
        raise
    return dest_path


class HandTracker:
    """
    Captures webcam frames, detects hand landmarks via MediaPipe Tasks API,
    runs gesture recognition, and triggers keyboard actions.
    """

    def __init__(self, overlay=None):
        self.overlay = overlay
        self.gesture_engine = GestureEngine()
        self.controller = Controller()
        self.mouse_controller = MouseController()

        self.biometrics = HandBiometrics()
        
        # State
        self._state = STATE_SLEEPING if self.biometrics.has_profile() else STATE_REGISTERING
        self._activation_start = 0.0
        self._last_hand_seen = 0.0
        self._running = False
        self._thread = None
        self._cap = None
        self._landmarker = None
        
        # Zero-Latency Pipeline variables
        self._camera_running = False
        self._camera_thread = None
        self._latest_frame = None
        self._frame_lock = threading.Lock()

        # Model path (same directory as this script)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self._model_path = os.path.join(script_dir, MODEL_FILENAME)

    @property
    def state(self):
        return self._state

    @property
    def is_running(self):
        return self._running

    def start(self):
        """Start the tracking loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        print("[HandTracker] Tracking started")

    def stop(self):
        """Stop the tracking loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._cleanup()
        print("[HandTracker] Tracking stopped")



    # ──────────────────────────────────────────────
    # Drawing helpers (replaces mp.solutions.drawing_utils)
    # ──────────────────────────────────────────────

    @staticmethod
    def _draw_landmarks_on_frame(frame, landmarks, width, height):
        """Draw hand landmarks and connections on the frame."""
        # Draw connections
        for start_idx, end_idx in HAND_CONNECTIONS:
            start = landmarks[start_idx]
            end = landmarks[end_idx]
            x1, y1 = int(start.x * width), int(start.y * height)
            x2, y2 = int(end.x * width), int(end.y * height)
            cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 128), 2)

        # Draw landmark points
        for i, lm in enumerate(landmarks):
            x, y = int(lm.x * width), int(lm.y * height)
            # Fingertips get larger dots
            if i in (4, 8, 12, 16, 20):
                cv2.circle(frame, (x, y), 6, (0, 200, 255), -1)
                cv2.circle(frame, (x, y), 6, (255, 255, 255), 1)
            else:
                cv2.circle(frame, (x, y), 3, (0, 128, 255), -1)

    # ──────────────────────────────────────────────
    # Main Tracking Loop
    # ──────────────────────────────────────────────

    def _tracking_loop(self):
        """Main loop: capture → detect → classify → act. Runs in background thread."""

        # Download model if needed
        try:
            download_model(self._model_path)
        except Exception:
            self._running = False
            if self.overlay:
                self.overlay.show_action("❌", "Model download failed")
            return

        # Open camera (using DirectShow backend for better Windows compatibility)
        self._cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

        if not self._cap.isOpened():
            print("[HandTracker] ERROR: Could not open camera")
            self._running = False
            if self.overlay:
                self.overlay.show_action("❌", "Camera not available")
            return

        # Initialize MediaPipe HandLandmarker (Tasks API)
        try:
            base_options = mp_tasks.BaseOptions(
                model_asset_path=self._model_path
            )
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO,
                num_hands=MAX_NUM_HANDS,
                min_hand_detection_confidence=MIN_DETECTION_CONFIDENCE,
                min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[HandTracker] ERROR initializing HandLandmarker: {e}")
            self._running = False
            if self.overlay:
                self.overlay.show_action("❌", "HandLandmarker init failed")
            return

        print("[HandTracker] Camera opened, MediaPipe HandLandmarker initialized")

        frame_timestamp_ms = 0
        
        # Start the Zero-Latency Camera Thread
        self._camera_running = True
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()

        while self._running:
            with self._frame_lock:
                if self._latest_frame is None:
                    frame = None
                else:
                    frame = self._latest_frame
                    self._latest_frame = None  # Consume the frame
                    
            if frame is None:
                time.sleep(0.005)  # Let CPU rest while waiting for the next camera frame
                continue

            h, w, _ = frame.shape

            # Convert BGR → RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Create MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            # Run hand detection with monotonically increasing timestamp
            frame_timestamp_ms += 33  # ~30fps
            try:
                results = self._landmarker.detect_for_video(mp_image, frame_timestamp_ms)
            except Exception as e:
                continue

            now = time.time()

            if results.hand_landmarks and results.handedness:
                self._last_hand_seen = now

                # Process first detected hand
                landmarks = results.hand_landmarks[0]  # List of NormalizedLandmark
                handedness = results.handedness[0][0].category_name  # "Left" or "Right"

                raw_gesture = self._process_hand(landmarks, handedness, now)

                # Draw hand skeleton for the Smart HUD
                self._draw_landmarks_on_frame(frame, landmarks, w, h)
                if raw_gesture:
                    cv2.putText(
                        frame, f"Gesture: {raw_gesture}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (255, 255, 0), 2,
                    )
            else:
                # No hand detected
                self._handle_no_hand(now)

            # Push the final frame to the unified GUI
            if self.overlay:
                self.overlay.update_frame(frame)

        self._cleanup()

    # ──────────────────────────────────────────────
    # State Machine
    # ──────────────────────────────────────────────

    def _process_hand(self, landmarks, handedness, now):
        """Process detected hand landmarks through the state machine."""

        # ── Biometric Authentication ──
        physical_hand = "Right" if handedness == "Left" else "Left"
        if self._state != STATE_REGISTERING:
            is_auth, dist = self.biometrics.authenticate(landmarks, physical_hand)
            if not is_auth:
                print(f"[HandTracker] Intruder blocked! ({physical_hand} hand, Dist: {dist:.3f})")
                if self.overlay:
                    # Throttle overlay spam
                    if now - getattr(self, '_last_intruder_time', 0) > 1.0:
                        self.overlay.show_action("🛑", "Intruder Blocked")
                        self._last_intruder_time = now
                return "INTRUDER"

        # ── STATE: REGISTERING ──
        if self._state == STATE_REGISTERING:
            # MediaPipe's "Left" is the physical right hand when the webcam is mirrored.
            # We want to use the physical hand names for the UI and the Biometrics engine.
            physical_hand = "Right" if handedness == "Left" else "Left"
            
            progress_l = self.biometrics.get_scan_progress("Left", 100)
            progress_r = self.biometrics.get_scan_progress("Right", 100)
            
            # Sequence: Left Hand first, then Right Hand
            target_hand = "Left" if progress_l < 1.0 else "Right"
            
            raw_gesture = self.gesture_engine._classify_gesture(landmarks, handedness)
            
            if raw_gesture == GESTURE_OPEN_HAND:
                if physical_hand == target_hand:
                    # Add scan using the PHYSICAL hand name
                    self.biometrics.add_scan(landmarks, physical_hand)
                    
                    # Recalculate
                    progress_l = self.biometrics.get_scan_progress("Left", 100)
                    progress_r = self.biometrics.get_scan_progress("Right", 100)
                    
                    if progress_l < 1.0:
                        status_msg = f"Scanning Left Hand... {progress_l*100:.0f}%"
                    elif progress_r < 1.0:
                        status_msg = f"Scanning Right Hand... {progress_r*100:.0f}%"
                    else:
                        status_msg = "Finalizing..."
                    
                    print(f"[HandTracker] {status_msg}")
                    if self.overlay:
                        self.overlay.show_action("✋", status_msg)
                        
                    if progress_l >= 1.0 and progress_r >= 1.0:
                        if self.biometrics.finalize_registration():
                            self._state = STATE_SLEEPING
                            print("[HandTracker] Dual Registration Complete! Sleeping.")
                            if self.overlay:
                                self.overlay.show_action("✅", "Both Hands Registered")
                else:
                    if self.overlay:
                        self.overlay.show_action("✋", f"Please show your {target_hand} Hand")
            else:
                if self.overlay:
                    self.overlay.show_action("✋", f"Show Open {target_hand} Hand")
            return raw_gesture

        # ── Get gesture from engine for normal operation ──
        result = self.gesture_engine.process(landmarks, handedness)
        # Convert to physical handedness for the gesture engine output if needed, but it handles it internally.
        physical_hand = "Right" if handedness == "Left" else "Left"
        raw_gesture = result["raw_gesture"]
        confirmed = result["gesture"]
        triggered = result["triggered"]
        swipe = result["swipe"]

        # ── STATE: SLEEPING ──
        if self._state == STATE_SLEEPING:
            if raw_gesture == GESTURE_OPEN_HAND:
                self._state = STATE_ACTIVATING
                self._activation_start = now
                if self.overlay:
                    self.overlay.set_state(STATE_ACTIVATING)
                print("[HandTracker] Open hand detected -- activating...")

        # ── STATE: ACTIVATING ──
        elif self._state == STATE_ACTIVATING:
            if raw_gesture == GESTURE_OPEN_HAND:
                # Check if held long enough
                if now - self._activation_start >= ACTIVATION_HOLD_TIME:
                    self._state = STATE_READY
                    if self.overlay:
                        self.overlay.set_state(STATE_READY)
                        self.overlay.show_action("✋", "Controller Activated!")
                    print("[HandTracker] ACTIVATED -- Ready for commands")
            else:
                # Hand changed — go back to sleep
                self._state = STATE_SLEEPING
                if self.overlay:
                    self.overlay.set_state(STATE_SLEEPING)

        # ── STATE: READY ──
        elif self._state == STATE_READY:
            # Handle swipe (seeking)
            if swipe:
                action = self.controller.execute_swipe(swipe)
                if action and self.overlay:
                    self.overlay.show_action(action["emoji"], action["label"])
                print(f"[HandTracker] Swipe: {swipe} -> {action['label'] if action else 'N/A'}")
                return

            # In Ambidextrous Mode, GESTURE_FIST is a mouse click on the Right Hand, but Play/Pause on the Left Hand.
            is_physical_right = (handedness == "Left")
            if is_physical_right and AMBIDEXTROUS_MODE:
                mouse_gestures = (GESTURE_L_SHAPE, GESTURE_POINTING, GESTURE_FIST)
            else:
                mouse_gestures = (GESTURE_L_SHAPE, GESTURE_POINTING)

            # Handle confirmed gestures (ignore OPEN_HAND and mouse gestures in ready state)
            if triggered and confirmed not in (GESTURE_NONE, GESTURE_OPEN_HAND) and confirmed not in mouse_gestures:
                action = self.controller.execute_gesture(confirmed)
                if action and self.overlay:
                    self.overlay.show_action(action["emoji"], action["label"])
                print(f"[HandTracker] Gesture: {confirmed} -> {action['label'] if action else 'N/A'}")
            
            # Handle Mouse Control
            if raw_gesture in mouse_gestures:
                self.mouse_controller.update(result["pointer_x"], result["pointer_y"], raw_gesture)
            else:
                self.mouse_controller.reset()
                
        return raw_gesture

    def _handle_no_hand(self, now):
        """Handle frames where no hand is detected."""
        if self._state == STATE_ACTIVATING:
            self._state = STATE_SLEEPING
            if self.overlay:
                self.overlay.set_state(STATE_SLEEPING)

        elif self._state == STATE_READY:
            if now - self._last_hand_seen >= DEACTIVATION_TIMEOUT:
                self._state = STATE_SLEEPING
                self.gesture_engine.reset()
                self.mouse_controller.reset()
                if self.overlay:
                    self.overlay.set_state(STATE_SLEEPING)
                    self.overlay.show_action("😴", "Controller Deactivated")
                print("[HandTracker] No hand for 3s -- deactivated")

    # ──────────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────────

    def _cleanup(self):
        """Release camera and close windows."""
        self._camera_running = False
        if hasattr(self, '_camera_thread') and self._camera_thread:
            self._camera_thread.join(timeout=1.0)
            self._camera_thread = None
            
        if self._cap and self._cap.isOpened():
            self._cap.release()
            self._cap = None
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        self._state = STATE_SLEEPING
        self.gesture_engine.reset()
        if hasattr(self, 'mouse_controller'):
            self.mouse_controller.reset()

    # ──────────────────────────────────────────────
    # Zero-Latency Camera Loop
    # ──────────────────────────────────────────────
    
    def _camera_loop(self):
        """
        Runs in a dedicated background thread. 
        Constantly pulls frames from OpenCV as fast as the webcam allows.
        This prevents the internal DirectShow buffer from backing up, 
        guaranteeing that the AI thread always gets a 0ms-latency fresh frame!
        """
        while self._camera_running and self._cap and self._cap.isOpened():
            success, frame = self._cap.read()
            if success:
                # Flip here to save time on the AI thread
                frame = cv2.flip(frame, 1)
                with self._frame_lock:
                    self._latest_frame = frame
            else:
                time.sleep(0.01)
