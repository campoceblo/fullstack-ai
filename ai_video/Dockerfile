FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-venv \
      python3-pip \
      build-essential \
      git \
      wget \
      ca-certificates \
      curl \
      ffmpeg \
      libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN pip install --upgrade pip setuptools wheel && \
    pip install \
      fastapi \
      uvicorn[standard] \
      sqlalchemy \
      psycopg2-binary \
      minio \
      python-dotenv \
      python-multipart \
      librosa \
      soundfile \
      --no-cache-dir

RUN pip install huggingface_hub

WORKDIR /app
RUN git clone https://github.com/bytedance/LatentSync.git 

RUN mkdir -p checkpoints && \
    huggingface-cli download ByteDance/LatentSync-1.6 latentsync_unet.pt --local-dir checkpoints && \
    huggingface-cli download ByteDance/LatentSync-1.6 whisper/tiny.pt --local-dir checkpoints

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/LatentSync
COPY process_video.py /app/process_video.py

EXPOSE 8000

CMD ["uvicorn", "process_video:app", "--host", "0.0.0.0", "--port", "8000"]
