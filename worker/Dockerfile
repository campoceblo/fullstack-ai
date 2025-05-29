FROM python:3.11-slim

# System dependencies
RUN apt-get update && \
    apt-get install -y git ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /worker

# Install Python deps (including Chatterbox via pip)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your worker script
COPY worker.py .

# Start the worker
CMD ["python", "worker.py"]
