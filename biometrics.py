"""
Biometric Hand Registration Engine
Extracts scale-invariant geometric ratios from hand landmarks to create a unique profile.
Supports both Left and Right hands independently.
"""

import math
import json
import os
from config import (
    WRIST, INDEX_MCP, INDEX_TIP,
    MIDDLE_MCP, MIDDLE_TIP,
    RING_MCP, RING_TIP,
    PINKY_MCP, PINKY_TIP,
    CAMERA_WIDTH, CAMERA_HEIGHT
)

PROFILE_PATH = "profile.json"
# The maximum allowed Euclidean distance between a live scan and the registered profile
AUTH_THRESHOLD = 1.5 

class HandBiometrics:
    def __init__(self):
        self.profiles = {"Left": None, "Right": None}
        self._scans = {"Left": [], "Right": []}
        self.load_profile()

    def _distance(self, p1, p2):
        # Calculate 2D Euclidean distance in uniform pixel space.
        # We explicitly ignore Z (depth) because MediaPipe's Z coordinate is highly noisy and ruins scale invariance.
        dx = (p1.x - p2.x) * CAMERA_WIDTH
        dy = (p1.y - p2.y) * CAMERA_HEIGHT
        return math.sqrt(dx*dx + dy*dy)

    def _extract_features(self, landmarks):
        """
        Extracts 7 scale-invariant geometric ratios from the rigid palm structure.
        Using MCPs (knuckles) and Wrist ensures the signature remains constant 
        even when the user bends their fingers into different gestures.
        """
        wrist = landmarks[WRIST]
        index_mcp = landmarks[INDEX_MCP]
        middle_mcp = landmarks[MIDDLE_MCP]
        ring_mcp = landmarks[RING_MCP]
        pinky_mcp = landmarks[PINKY_MCP]

        # Base reference: Palm height (Wrist to Middle Knuckle)
        palm_height = self._distance(wrist, middle_mcp)
        
        if palm_height < 0.001:
            return None

        # Rigid metacarpal distances
        wrist_to_index = self._distance(wrist, index_mcp)
        wrist_to_ring = self._distance(wrist, ring_mcp)
        wrist_to_pinky = self._distance(wrist, pinky_mcp)
        
        index_to_middle = self._distance(index_mcp, middle_mcp)
        middle_to_ring = self._distance(middle_mcp, ring_mcp)
        ring_to_pinky = self._distance(ring_mcp, pinky_mcp)
        index_to_pinky = self._distance(index_mcp, pinky_mcp) # Total palm width

        # Scale-invariant ratios
        return [
            wrist_to_index / palm_height,
            wrist_to_ring / palm_height,
            wrist_to_pinky / palm_height,
            index_to_middle / palm_height,
            middle_to_ring / palm_height,
            ring_to_pinky / palm_height,
            index_to_pinky / palm_height
        ]

    def add_scan(self, landmarks, handedness):
        """Add a frame to the registration pool for a specific hand."""
        if handedness not in self._scans:
            print(f"[DEBUG] add_scan failed: {handedness} not in _scans")
            return
            
        features = self._extract_features(landmarks)
        if features:
            self._scans[handedness].append(features)
            print(f"[DEBUG] add_scan SUCCESS! len({handedness}) is now {len(self._scans[handedness])}")
        else:
            print(f"[DEBUG] add_scan failed: features is None")
            
    def get_scan_progress(self, handedness, required_scans):
        """Returns the current progress of registration (0.0 to 1.0) for a specific hand."""
        if handedness not in self._scans:
            return 0.0
        return min(1.0, len(self._scans[handedness]) / required_scans)

    def finalize_registration(self):
        """Averages the collected scans and saves the profiles to disk."""
        if not self._scans["Left"] or not self._scans["Right"]:
            return False

        num_features = len(self._scans["Left"][0])

        for hand in ["Left", "Right"]:
            avg_features = [0.0] * num_features
            for scan in self._scans[hand]:
                for i in range(num_features):
                    avg_features[i] += scan[i]
            self.profiles[hand] = [val / len(self._scans[hand]) for val in avg_features]
        
        # Save to disk
        try:
            with open(PROFILE_PATH, 'w') as f:
                json.dump({"biometric_signatures": self.profiles}, f)
            print(f"[Biometrics] Dual profiles saved successfully.")
            self._scans = {"Left": [], "Right": []}
            return True
        except Exception as e:
            print(f"[Biometrics] Error saving profiles: {e}")
            return False

    def load_profile(self):
        """Loads existing dual profiles from disk."""
        if os.path.exists(PROFILE_PATH):
            try:
                with open(PROFILE_PATH, 'r') as f:
                    data = json.load(f)
                    if "biometric_signatures" in data:
                        self.profiles = data["biometric_signatures"]
                        print("[Biometrics] Dual profiles loaded successfully.")
                        return True
            except Exception as e:
                print(f"[Biometrics] Error loading profiles: {e}")
        return False

    def has_profile(self):
        """Returns True if both Left and Right profiles exist."""
        return self.profiles.get("Left") is not None and self.profiles.get("Right") is not None

    def authenticate(self, landmarks, handedness):
        """
        Compare current hand against its registered profile.
        Returns (is_authenticated, distance).
        """
        profile = self.profiles.get(handedness)
        if not profile:
            return True, 0.0  # Allow all if no profile is set for this hand

        features = self._extract_features(landmarks)
        if not features:
            return False, 999.0

        # Calculate Euclidean distance between current hand signature and saved profile
        dist = 0.0
        for i in range(len(profile)):
            dist += (features[i] - profile[i]) ** 2
        
        euclidean_dist = math.sqrt(dist)
        
        is_authenticated = euclidean_dist <= AUTH_THRESHOLD
        return is_authenticated, euclidean_dist
