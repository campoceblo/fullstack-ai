import os
from redis import Redis
from rq import Worker, Queue, Connection
import boto3
import shutil
import torchaudio as ta

# Chatterbox import
from chatterbox.tts import ChatterboxTTS

# ─── Init TTS model once ───────────────────────────────────────────────────────
# loads the pretrained model onto GPU (or CPU if you prefer)
model = ChatterboxTTS.from_pretrained(device="cuda")

# ─── Init Redis + RQ ───────────────────────────────────────────────────────────
redis_conn = Redis.from_url(os.getenv("REDIS_URL"))
q = Queue(connection=redis_conn)

# ─── Init S3 (MinIO) client ────────────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("MINIO_URL"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
)
BUCKET = "tasks"

def process_job(job_id):
    # 1) Download the uploaded audio (optional prompt)
    audio_path = f"/tmp/{job_id}_audio.wav"
    s3.download_file(BUCKET, f"{job_id}/audio", audio_path)

    # 2) Download & read the user’s text
    text_path = f"/tmp/{job_id}_text.txt"
    s3.download_file(BUCKET, f"{job_id}/text", text_path)
    with open(text_path, "r", encoding="utf-8") as f:
        gen_text = f.read().strip()
    if not gen_text:
        raise ValueError(f"Job {job_id} had empty text")

    # 3) Generate audio with ChatterboxTTS
    #    If you want style transfer, pass audio_prompt_path=audio_path
    wav_tensor = model.generate(gen_text, audio_prompt_path=audio_path)

    # 4) Save to WAV on local temp
    out_wav = f"/tmp/{job_id}_out.wav"
    ta.save(out_wav, wav_tensor, model.sr)

    # 5) Upload WAV back to MinIO with .wav key
    with open(out_wav, "rb") as f:
        s3.upload_fileobj(f, BUCKET, f"{job_id}/output.wav")

    # 6) (Optional) Copy to a host-visible folder
    os.makedirs("./output", exist_ok=True)
    shutil.copy(out_wav, "./output/output.wav")

# ─── Worker loop ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    with Connection(redis_conn):
        Worker(q).work()
