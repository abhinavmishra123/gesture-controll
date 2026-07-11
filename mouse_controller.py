"""
Mouse Controller v3 — Precision Pipeline
==========================================
Translates normalized hand coordinates to smooth screen cursor movements.

PIPELINE (per frame):
  Raw MediaPipe → Kalman Filter (predict + smooth) → 1-Euro Filter (jitter kill)
  → Adaptive Deadband → S-Curve Acceleration → Sub-pixel Accumulation → OS Cursor

Techniques used:
  1. Kalman Filter:    Predicts hand position using a constant-velocity physics model.
                       Eliminates random MediaPipe jitter at the source.
  2. 1-Euro Filter:    Speed-adaptive low-pass on top of Kalman output.
                       Slow = heavy smoothing (rock solid), Fast = low smoothing (responsive).
  3. Adaptive Deadband: Deadband radius shrinks when moving fast, grows when still.
                        Prevents "staircase" stepping AND micro-drift simultaneously.
  4. S-Curve Accel:    Sigmoid-based acceleration curve instead of power curve.
                       Provides buttery smooth ramp-up instead of sudden jumps.
  5. Velocity Damping: When hand decelerates, cursor slows proportionally.
                       Prevents overshoot at the end of a flick.
"""

import time
import math
import ctypes
from collections import deque
from config import (
    FILTER_MIN_CUTOFF, FILTER_BETA, TRACKPAD_SENSITIVITY, MOUSE_SCROLL_SPEED,
    DEADBAND_RADIUS, ACCELERATION_THRESHOLD, MOUSE_ACCELERATION_FACTOR,
    GESTURE_L_SHAPE, GESTURE_POINTING, GESTURE_FIST
)
from one_euro_filter import OneEuroFilter
from kalman_filter import KalmanFilter2D

# ══════════════════════════════════════════
# Advanced Physics Constants
# ══════════════════════════════════════════
KALMAN_PROCESS_NOISE = 0.008      # Lower = smoother Kalman output (trust physics more)
KALMAN_MEASUREMENT_NOISE = 0.06   # Higher = ignore more MediaPipe jitter

# S-Curve acceleration parameters
SCURVE_MIDPOINT = 20.0            # Pixel speed where acceleration = 1x (the inflection point)
SCURVE_STEEPNESS = 0.15           # How sharply the curve transitions (lower = gentler ramp)
SCURVE_MAX_MULTIPLIER = 3.5       # Maximum acceleration cap (prevents teleporting)
SCURVE_MIN_MULTIPLIER = 0.3       # Minimum deceleration for precision micro-movements

# Adaptive deadband
DEADBAND_MIN = 0.3                # Minimum deadband when moving fast (pixels)
DEADBAND_MAX = 2.0                # Maximum deadband when stationary (pixels)
DEADBAND_DECAY = 0.92             # How quickly deadband shrinks when moving (per frame)

# Velocity damping
DAMPING_THRESHOLD = 5.0           # Below this speed (px/frame), apply deceleration damping
DAMPING_FACTOR = 0.7              # Multiply movement by this when decelerating


class MouseController:
    """Smoothly controls the mouse cursor using hand coordinates."""

    def __init__(self):
        # Get actual screen dimensions using ctypes for zero dependency
        self.screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        self.screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        # ── Tracking State ──
        self.last_hand_x = -1.0
        self.last_hand_y = -1.0

        # Absolute cursor position on OS (sub-pixel precision)
        self.cursor_x = -1.0
        self.cursor_y = -1.0

        # ── Filter Pipeline ──
        self.kalman = KalmanFilter2D(
            process_noise=KALMAN_PROCESS_NOISE,
            measurement_noise=KALMAN_MEASUREMENT_NOISE,
        )
        self.euro_x = None   # 1-Euro on top of Kalman
        self.euro_y = None

        # ── Adaptive Deadband ──
        self.current_deadband = DEADBAND_MAX

        # ── Velocity History (for damping) ──
        self.velocity_history = deque(maxlen=5)

        # ── Click State ──
        self.is_dragging = False
        self.last_pinch_state = False
        self.pinch_start_time = 0.0

        # ── Scroll State ──
        self.scroll_anchor_y = -1
        self.scroll_accumulator = 0.0   # Sub-pixel scroll accumulation

    def reset(self):
        """Reset state when tracking stops or hand is lost."""
        self.last_hand_x = -1.0
        self.last_hand_y = -1.0
        self.cursor_x = -1.0
        self.cursor_y = -1.0
        self.kalman = KalmanFilter2D(
            process_noise=KALMAN_PROCESS_NOISE,
            measurement_noise=KALMAN_MEASUREMENT_NOISE,
        )
        self.euro_x = None
        self.euro_y = None
        self.current_deadband = DEADBAND_MAX
        self.velocity_history.clear()

        self.scroll_anchor_y = -1
        self.scroll_accumulator = 0.0
        if self.is_dragging:
            try:
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # Mouse Up
            except Exception:
                pass
            self.is_dragging = False

    # ══════════════════════════════════════════
    # S-Curve Acceleration
    # ══════════════════════════════════════════

    @staticmethod
    def _scurve_acceleration(speed_px):
        """
        Attempt 3: S-Curve (Sigmoid) acceleration.
        
        Unlike power curves (x^1.35) which have a sharp elbow,
        a sigmoid provides a smooth, continuous ramp:
        
          - Very slow movement → multiplier ≈ SCURVE_MIN_MULTIPLIER (heavy decel)
          - Medium movement    → multiplier ≈ 1.0 (linear, natural)
          - Fast movement      → multiplier → SCURVE_MAX_MULTIPLIER (capped accel)
        
        This feels like a high-end trackpad because there are no sudden
        changes in cursor behavior at any speed.
        """
        # Sigmoid: f(x) = L / (1 + e^(-k*(x-x0)))
        # We map it to [MIN, MAX] range
        exponent = -SCURVE_STEEPNESS * (speed_px - SCURVE_MIDPOINT)
        exponent = max(-20.0, min(20.0, exponent))  # Clamp to prevent overflow
        sigmoid = 1.0 / (1.0 + math.exp(exponent))

        # Map sigmoid [0, 1] → [MIN_MULTIPLIER, MAX_MULTIPLIER]
        multiplier = SCURVE_MIN_MULTIPLIER + sigmoid * (SCURVE_MAX_MULTIPLIER - SCURVE_MIN_MULTIPLIER)
        return multiplier

    # ══════════════════════════════════════════
    # Main Update (called every frame)
    # ══════════════════════════════════════════

    def update(self, norm_x, norm_y, gesture_name):
        """
        Update the mouse position and click/scroll state.
        Called every frame when hand is active.
        """
        now = time.time()

        # ══════════════════════════════════════
        # STAGE 1: Kalman Filter (Prediction + Noise Rejection)
        # ══════════════════════════════════════
        kx, ky, kvx, kvy = self.kalman.update(norm_x, norm_y, now)

        # ══════════════════════════════════════
        # STAGE 2: 1-Euro Filter (Speed-Adaptive Jitter Kill)
        # ══════════════════════════════════════
        if self.last_hand_x == -1.0:
            # First frame: initialize everything
            self.euro_x = OneEuroFilter(now, kx, min_cutoff=FILTER_MIN_CUTOFF, beta=FILTER_BETA)
            self.euro_y = OneEuroFilter(now, ky, min_cutoff=FILTER_MIN_CUTOFF, beta=FILTER_BETA)

            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            self.cursor_x = float(pt.x)
            self.cursor_y = float(pt.y)

            self.last_hand_x = kx
            self.last_hand_y = ky
            return

        smooth_x = self.euro_x(now, kx)
        smooth_y = self.euro_y(now, ky)

        # ══════════════════════════════════════
        # STAGE 3: Click Logic (1:1 Mapping)
        # ══════════════════════════════════════
        is_pinching = (gesture_name == GESTURE_FIST)

        # Edge Detection
        just_pressed = is_pinching and not self.last_pinch_state
        self.last_pinch_state = is_pinching

        if just_pressed:
            self.pinch_start_time = now

        # Determine target physical mouse state
        target_dragging = is_pinching

        # Apply physical mouse state
        if target_dragging and not self.is_dragging:
            self.is_dragging = True
            try:
                ctypes.windll.user32.SetCursorPos(int(self.cursor_x), int(self.cursor_y))
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # Mouse Down
            except Exception:
                pass
        elif not target_dragging and self.is_dragging:
            self.is_dragging = False
            try:
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # Mouse Up
            except Exception:
                pass

        # CURSOR FREEZE during click initiation
        if is_pinching and (now - self.pinch_start_time < 0.25):
            self.last_hand_x = smooth_x
            self.last_hand_y = smooth_y
            return

        # ══════════════════════════════════════
        # STAGE 4: Scroll Logic (L-Shape)
        # ══════════════════════════════════════
        if gesture_name == GESTURE_L_SHAPE:
            if self.scroll_anchor_y == -1:
                self.scroll_anchor_y = norm_y
            else:
                delta_y = norm_y - self.scroll_anchor_y
                if abs(delta_y) > 0.03:
                    # Smooth scroll with sub-pixel accumulation
                    active_delta = (abs(delta_y) - 0.03) * (1 if delta_y > 0 else -1)
                    self.scroll_accumulator += -active_delta * 80
                    
                    # Only scroll when we've accumulated a full click
                    scroll_int = int(self.scroll_accumulator)
                    if scroll_int != 0:
                        try:
                            ctypes.windll.user32.mouse_event(0x0800, 0, 0, scroll_int, 0)
                        except Exception:
                            pass
                        self.scroll_accumulator -= scroll_int

            self.last_hand_x = smooth_x
            self.last_hand_y = smooth_y
            return
        else:
            self.scroll_anchor_y = -1
            self.scroll_accumulator = 0.0

        # ══════════════════════════════════════
        # STAGE 5: Calculate Movement Delta
        # ══════════════════════════════════════
        dx = smooth_x - self.last_hand_x
        dy = smooth_y - self.last_hand_y

        # Convert to pixel units
        delta_px_x = dx * self.screen_w * TRACKPAD_SENSITIVITY
        delta_px_y = dy * self.screen_h * TRACKPAD_SENSITIVITY

        raw_speed = math.hypot(delta_px_x, delta_px_y)

        # ══════════════════════════════════════
        # STAGE 6: Adaptive Deadband
        # ══════════════════════════════════════
        # When moving: deadband shrinks rapidly (responsive)
        # When still: deadband grows back (stable)
        if raw_speed > self.current_deadband:
            # Moving! Shrink the deadband for responsiveness
            self.current_deadband = max(DEADBAND_MIN, self.current_deadband * DEADBAND_DECAY)
        else:
            # Still! Grow the deadband to lock the cursor solid
            self.current_deadband = min(DEADBAND_MAX, self.current_deadband + 0.1)
            return  # Don't move

        # Commit the hand position
        self.last_hand_x = smooth_x
        self.last_hand_y = smooth_y

        # ══════════════════════════════════════
        # STAGE 7: S-Curve Acceleration
        # ══════════════════════════════════════
        accel = self._scurve_acceleration(raw_speed)

        # ══════════════════════════════════════
        # STAGE 8: Velocity Damping (Overshoot Prevention)
        # ══════════════════════════════════════
        self.velocity_history.append(raw_speed)

        if len(self.velocity_history) >= 3:
            # Check if we're decelerating (recent speed < older speed)
            recent_avg = sum(list(self.velocity_history)[-2:]) / 2
            older_avg = sum(list(self.velocity_history)[:2]) / 2

            if recent_avg < older_avg and raw_speed < DAMPING_THRESHOLD:
                # Hand is slowing down — apply damping to prevent overshoot
                accel *= DAMPING_FACTOR

        # Apply acceleration
        final_dx = delta_px_x * accel
        final_dy = delta_px_y * accel

        # Sub-pixel accumulation (keeps fractional pixels for next frame)
        self.cursor_x += final_dx
        self.cursor_y += final_dy

        # Clamp to screen bounds
        self.cursor_x = max(0, min(self.screen_w - 1, self.cursor_x))
        self.cursor_y = max(0, min(self.screen_h - 1, self.cursor_y))

        # ══════════════════════════════════════
        # STAGE 9: Move Physical Mouse
        # ══════════════════════════════════════
        try:
            ctypes.windll.user32.SetCursorPos(int(self.cursor_x), int(self.cursor_y))
        except Exception:
            pass
