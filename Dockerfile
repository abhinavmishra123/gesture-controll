FROM python:3.10-slim

WORKDIR /app

# Install system dependencies required for OpenCV and GUI
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    tk-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# IMPORTANT LIMITATION:
# This application relies on Windows OS APIs (ctypes.windll.user32) for mouse control,
# and global keyboard hooks. Running it inside a standard Linux Docker container
# will cause it to fail since the Windows DLLs and host interactive desktop are missing.
# Dockerizing GUI apps that control the host mouse/keyboard is highly experimental.
# This Dockerfile is provided as a starting point if cross-platform (Linux X11/Wayland)
# support is added in the future.

CMD ["python", "main.pyw"]
