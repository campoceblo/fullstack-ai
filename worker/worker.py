import os, subprocess
from redis import Redis
from rq import Worker, Queue
from rq import Connection
import boto3
import shutil

# Init Redis + RQ
redis_conn = Redis.from_url(os.getenv("REDIS_URL"))
q = Queue(connection=redis_conn)
# Init S3 client
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("MINIO_URL"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
)
BUCKET = "tasks"

def process_job(job_id):
    # 1) Download the uploaded audio
    audio_path = f"/tmp/{job_id}_audio.wav"
    s3.download_file(BUCKET, f"{job_id}/audio", audio_path)

    # 2) Download and read the user’s text
    text_path = f"/tmp/{job_id}_text.txt"
    s3.download_file(BUCKET, f"{job_id}/text", text_path)
    with open(text_path, "r", encoding="utf-8") as f:
        gen_text = f.read().strip()
    if not gen_text:
        raise ValueError(f"Job {job_id} had empty text")

    out_path = f"/tmp/{job_id}_out.mp3"
    subprocess.run([
        "f5-tts_infer-cli",
        "--model",     "F5TTS_v1_Base",
        "--ref_audio", audio_path,
        "--ref_text",  "",          # leave this empty for ASR-based ref-text
        "--gen_text",  gen_text,    # ← now defined!
        "--output_file", out_path,
        "--device", "cuda",
    ], check=True)

                              
    with open(out_path, "rb") as f:
        s3.upload_fileobj(f, BUCKET, f"{job_id}/output.mp3")

# Start worker process when container runs
if __name__ == '__main__':
    with Connection(redis_conn):
        Worker(q).work()
