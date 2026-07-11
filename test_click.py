import ctypes
import time
print("Moving to 100, 100 and clicking")
ctypes.windll.user32.SetCursorPos(100, 100)
time.sleep(0.1)
ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.1)
ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
print("Done")
