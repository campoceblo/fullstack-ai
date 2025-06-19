FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-venv \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*


RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .

RUN grep -v "chatterbox" requirements.txt > requirements_nogit.txt

RUN pip install --upgrade pip setuptools wheel && \
    pip install \
      torch \
      torchvision \
      torchaudio \
      --index-url https://download.pytorch.org/whl/cu128 \
      --no-cache-dir && \
    pip install --no-cache-dir -r requirements_nogit.txt

RUN git clone https://github.com/resemble-ai/chatterbox.git /app/chatterbox && \
    pip install -e /app/chatterbox

COPY process_audio.py .
EXPOSE 8000
CMD ["python", "process_audio.py"]