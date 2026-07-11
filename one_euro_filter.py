import math
import time

def smoothing_factor(t_e, cutoff):
    """Calculate the exponential smoothing factor based on cutoff frequency."""
    r = 2 * math.pi * cutoff * t_e
    return r / (r + 1)

def exponential_smoothing(a, x, x_prev):
    """Standard exponential smoothing."""
    return a * x + (1 - a) * x_prev

class OneEuroFilter:
    """
    1 Euro Filter: A speed-based low-pass filter for noisy human motion.
    - Low speed = High smoothing (removes jitter when trying to hold still).
    - High speed = Low smoothing (removes lag/latency when moving quickly).
    """
    def __init__(self, t0, x0, dx0=0.0, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = float(x0)
        self.dx_prev = float(dx0)
        self.t_prev = float(t0)

    def __call__(self, t, x):
        """Filter a new incoming value."""
        t_e = t - self.t_prev
        if t_e <= 0.0:
            return self.x_prev # prevent divide by zero on simultaneous frames

        # 1. Filter the derivative (speed) of the signal
        dx = (x - self.x_prev) / t_e
        a_d = smoothing_factor(t_e, self.d_cutoff)
        dx_hat = exponential_smoothing(a_d, dx, self.dx_prev)

        # 2. Filter the signal dynamically based on speed
        # The faster we move (dx_hat), the higher the cutoff (less smoothing)
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = smoothing_factor(t_e, cutoff)
        x_hat = exponential_smoothing(a, x, self.x_prev)

        # 3. Memorize values for next frame
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        
        return x_hat
