# Hand Gesture Controller

Control your computer using nothing but your hands! This application uses your webcam to track your hand movements and lets you control your mouse, play/pause music, and more without touching your keyboard or mouse.

## Features

- **Right Hand = Mouse:** Point your index finger to move the mouse. Make a fist to click or drag.
- **Left Hand = Media Control:** Control your music or videos. Make a fist to play/pause, or a peace sign to mute.
- **Biometric Security:** The app remembers the exact shape of your hands. It won't work for anyone else!
- **Runs in the Background:** The app sits quietly in your Windows taskbar.
- **Global Hotkey:** Press `Ctrl + Alt + S` anytime to start or stop the camera tracking.

## How to Install

1. Make sure you have Python installed on your computer.
2. Download or clone this folder.
3. Open a terminal in this folder and install the required tools by running:
   ```bash
   pip install -r requirements.txt
   ```

## How to Run

To start the app silently in the background, double-click the `run_hidden.vbs` file. 

You can also run it manually from the terminal:
```bash
pythonw main.pyw
```
Once it starts, you will see a small icon in your taskbar.

## How to Use It

When you start the app for the very first time, it will ask you to show your open hands to the camera. This is the **Registration Phase**. It takes a few seconds to learn the exact size and shape of your hands for security.

### Waking it up
Hold an **Open Hand (✋)** for 2 seconds to wake up the system. (This stops accidental clicks when you are just moving around).

### Right Hand (Mouse Controls)
- **Move Mouse:** Point your index finger (👆).
- **Click:** Make a quick fist (✊) and open it.
- **Double Click:** Make a fist twice quickly.
- **Click and Drag:** Make a fist, hold it closed, and move your hand.
- **Scroll:** Make an L-shape with your thumb and index finger (👈) and move your hand up and down.

### Left Hand (Media Controls)
- **Play / Pause:** Make a fist (✊).
- **Next Track:** Give a thumbs up (👍).
- **Previous Track:** Pinch your thumb and index finger together (🤏).
- **Mute / Unmute:** Make a peace sign (✌️).

## Note on Docker
A `Dockerfile` is included for reference, but because this app controls the physical Windows mouse and keyboard, it is not meant to be run inside an isolated Docker container. Run it directly on your Windows machine for it to work properly.
