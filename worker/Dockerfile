FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel

WORKDIR /worker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


RUN apt-get update \
 && apt-get install -y git \
 && rm -rf /var/lib/apt/lists/*


RUN git clone https://github.com/SWivid/F5-TTS.git /workspace/F5-TTS \
 && cd /workspace/F5-TTS \
 && git submodule update --init --recursive \
 && pip install -e . --no-cache-dir

COPY worker.py .

CMD ["python", "worker.py"]
