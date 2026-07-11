"""
2D Kalman Filter with Velocity Prediction
==========================================
A state-of-the-art filtering approach for hand-tracking cursor control.

State vector: [x, y, vx, vy]  (position + velocity)
Measurement:  [x, y]          (raw landmark position)

The Kalman Filter does two things better than a 1-Euro filter:
1. PREDICTS where the hand will be next frame (reduces perceived latency)
2. Fuses noisy measurements with a physics model (smoother than any low-pass)

This implementation uses numpy-free pure Python for zero dependencies.
"""

import math


class KalmanFilter2D:
    """
    Constant-velocity 2D Kalman Filter.
    
    Tracks position and velocity in X and Y simultaneously.
    Uses a 4-dimensional state: [x, y, vx, vy]
    """

    def __init__(self, process_noise=0.01, measurement_noise=0.05):
        """
        Args:
            process_noise: How much we trust the physics model (lower = smoother but laggier)
            measurement_noise: How noisy the sensor is (higher = more smoothing)
        """
        # State vector [x, y, vx, vy]
        self.x = [0.0, 0.0, 0.0, 0.0]
        
        # Covariance matrix (4x4, stored as flat list for speed)
        # Initial high uncertainty
        self.P = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.initialized = False
        self.last_time = 0.0

    def _mat_mul_4x4(self, A, B):
        """Multiply two 4x4 matrices stored as flat 16-element lists."""
        C = [0.0] * 16
        for i in range(4):
            for j in range(4):
                s = 0.0
                for k in range(4):
                    s += A[i * 4 + k] * B[k * 4 + j]
                C[i * 4 + j] = s
        return C

    def _mat_add_4x4(self, A, B):
        """Add two 4x4 matrices."""
        return [A[i] + B[i] for i in range(16)]

    def _mat_transpose_4x4(self, A):
        """Transpose a 4x4 matrix."""
        T = [0.0] * 16
        for i in range(4):
            for j in range(4):
                T[j * 4 + i] = A[i * 4 + j]
        return T

    def reset(self, x, y, t):
        """Initialize or reset the filter with a known position."""
        self.x = [x, y, 0.0, 0.0]
        self.P = [
            0.1, 0.0, 0.0, 0.0,
            0.0, 0.1, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        self.last_time = t
        self.initialized = True

    def update(self, measured_x, measured_y, t):
        """
        Feed a new measurement and return the filtered (predicted) position.
        
        Args:
            measured_x: Raw X coordinate from MediaPipe
            measured_y: Raw Y coordinate from MediaPipe
            t: Current timestamp (seconds)
            
        Returns:
            (filtered_x, filtered_y, velocity_x, velocity_y)
        """
        if not self.initialized:
            self.reset(measured_x, measured_y, t)
            return measured_x, measured_y, 0.0, 0.0

        dt = t - self.last_time
        if dt <= 0.0:
            return self.x[0], self.x[1], self.x[2], self.x[3]
        self.last_time = t

        # Clamp dt to prevent explosions after pauses
        dt = min(dt, 0.1)

        # ════════════════════════════════════════
        # PREDICT STEP
        # ════════════════════════════════════════
        # State transition: x_new = x + vx*dt, y_new = y + vy*dt
        # F = [[1, 0, dt, 0],
        #      [0, 1, 0, dt],
        #      [0, 0, 1,  0],
        #      [0, 0, 0,  1]]
        
        # Predicted state
        px = self.x[0] + self.x[2] * dt
        py = self.x[1] + self.x[3] * dt
        pvx = self.x[2]
        pvy = self.x[3]
        x_pred = [px, py, pvx, pvy]

        # Predicted covariance: P = F * P * F^T + Q
        F = [
            1.0, 0.0, dt,  0.0,
            0.0, 1.0, 0.0, dt,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        Ft = self._mat_transpose_4x4(F)
        
        # Process noise Q scales with dt (faster movements = more uncertainty)
        q = self.process_noise
        Q = [
            q*dt**4/4, 0,         q*dt**3/2, 0,
            0,         q*dt**4/4, 0,         q*dt**3/2,
            q*dt**3/2, 0,         q*dt**2,   0,
            0,         q*dt**3/2, 0,         q*dt**2,
        ]
        
        FP = self._mat_mul_4x4(F, self.P)
        FPFt = self._mat_mul_4x4(FP, Ft)
        P_pred = self._mat_add_4x4(FPFt, Q)

        # ════════════════════════════════════════
        # UPDATE STEP
        # ════════════════════════════════════════
        # Measurement matrix H = [[1, 0, 0, 0],
        #                          [0, 1, 0, 0]]
        # We only measure position, not velocity.
        
        # Innovation (measurement residual)
        z = [measured_x, measured_y]
        y_innov = [z[0] - x_pred[0], z[1] - x_pred[1]]

        # Innovation covariance: S = H * P_pred * H^T + R
        # Since H selects rows 0,1, S is the top-left 2x2 of P_pred + R
        R = self.measurement_noise
        S00 = P_pred[0] + R
        S01 = P_pred[1]
        S10 = P_pred[4]
        S11 = P_pred[5] + R

        # Invert 2x2 matrix S
        det = S00 * S11 - S01 * S10
        if abs(det) < 1e-12:
            # Singular — skip update, return prediction
            self.x = x_pred
            self.P = P_pred
            return self.x[0], self.x[1], self.x[2], self.x[3]

        inv_det = 1.0 / det
        Si00 = S11 * inv_det
        Si01 = -S01 * inv_det
        Si10 = -S10 * inv_det
        Si11 = S00 * inv_det

        # Kalman Gain: K = P_pred * H^T * S^-1  (4x2 matrix)
        # K[i][j] = P_pred[i][0]*Si[0][j] + P_pred[i][1]*Si[1][j]
        K = [0.0] * 8  # 4x2
        for i in range(4):
            K[i * 2 + 0] = P_pred[i * 4 + 0] * Si00 + P_pred[i * 4 + 1] * Si10
            K[i * 2 + 1] = P_pred[i * 4 + 0] * Si01 + P_pred[i * 4 + 1] * Si11

        # Updated state: x = x_pred + K * y_innov
        self.x = [
            x_pred[0] + K[0] * y_innov[0] + K[1] * y_innov[1],
            x_pred[1] + K[2] * y_innov[0] + K[3] * y_innov[1],
            x_pred[2] + K[4] * y_innov[0] + K[5] * y_innov[1],
            x_pred[3] + K[6] * y_innov[0] + K[7] * y_innov[1],
        ]

        # Updated covariance: P = (I - K*H) * P_pred
        # KH is 4x4: KH[i][j] = K[i][0]*H[0][j] + K[i][1]*H[1][j]
        # Since H = [[1,0,0,0],[0,1,0,0]], KH[i][j] = K[i][j] for j<2, else 0
        IKH = [
            1.0 - K[0], -K[1],     0.0, 0.0,
            -K[2],      1.0 - K[3], 0.0, 0.0,
            -K[4],      -K[5],      1.0, 0.0,
            -K[6],      -K[7],      0.0, 1.0,
        ]
        self.P = self._mat_mul_4x4(IKH, P_pred)

        return self.x[0], self.x[1], self.x[2], self.x[3]

    @property
    def velocity(self):
        """Current estimated velocity magnitude."""
        return math.hypot(self.x[2], self.x[3])

    @property
    def position(self):
        """Current estimated position."""
        return self.x[0], self.x[1]
