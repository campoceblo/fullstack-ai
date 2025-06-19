# process_video.py

import os
import uuid
import subprocess
import tempfile
import shutil
import threading
import time

from fastapi import FastAPI, HTTPException, Form, Body
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()


minio_url = os.getenv("MINIO_URL", "minio:9000").replace("http://", "").replace("https://", "")
minio_client = Minio(
    minio_url,
    access_key=os.getenv("MINIO_ACCESS_KEY", "minio"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minio123"),
    secure=False
)


for bucket in ["videos", "audios", "outputs"]:
    try:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
    except S3Error:
        pass

DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://root:admin@postgres:5432/pgdb")
engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")

class InferenceParams(BaseModel):
    job_id: int
    unet_config_path: str = "configs/unet/stage2.yaml"
    inference_ckpt_path: str = "checkpoints/latentsync_unet.pt"
    inference_steps: int = 20
    guidance_scale: float = 2.0

def download_from_minio(minio_path: str, local_path: str):
    """
    minio_path: "bucket/object_name"
    local_path: filesystem path to write to
    """
    bucket, obj = minio_path.split("/", 1)
    try:
        response = minio_client.get_object(bucket, obj)
        with open(local_path, "wb") as f:
            for chunk in response.stream(32*1024):
                f.write(chunk)
        response.close()
        response.release_conn()
    except S3Error as e:
        raise RuntimeError(f"Failed to download {minio_path} from MinIO: {e}")

def upload_to_minio(local_path: str, bucket: str, object_name: str):
    """
    Upload a local file to MinIO and return the “bucket/object_name” path.
    """
    size = os.path.getsize(local_path)
    with open(local_path, "rb") as f:
        minio_client.put_object(bucket, object_name, f, size)
    return f"{bucket}/{object_name}"

def process_job_from_db(job_id, unet_config_path, inference_ckpt_path, inference_steps, guidance_scale):
    
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT path_minio_audio, path_minio_video_input FROM jobs WHERE id = :jid"),
            {"jid": job_id}
        )
        job = result.fetchone()
        if not job:
            print(f"Job {job_id} not found")
            return
        print(f"Fetched from DB for job {job_id}: path_minio_audio={job[0]}, path_minio_video_input={job[1]}")
        conn.execute(
            text("UPDATE jobs SET status = 'PROCESSING_VIDEO' WHERE id = :jid"),
            {"jid": job_id}
        )

    audio_minio_path, video_minio_path = job

    print(f"process_video: job_id={job_id}, audio_minio_path={audio_minio_path}, video_minio_path={video_minio_path}")

    if not audio_minio_path:
        print(f"No audio path in job (job_id={job_id}). Job: {job}")
        return

    working_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
    try:
        local_audio = os.path.join(working_dir, f"audio_{job_id}.wav")
        try:
            download_from_minio(audio_minio_path, local_audio)
        except Exception as e:
            print(f"Failed to download audio from MinIO for job {job_id}: {e}")
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE jobs SET status = 'FAILED' WHERE id = :jid"),
                    {"jid": job_id}
                )
            return

        local_video = None
        if video_minio_path:
            local_video = os.path.join(working_dir, f"video_input_{job_id}.mp4")
            try:
                download_from_minio(video_minio_path, local_video)
            except Exception as e:
                print(f"Failed to download video from MinIO for job {job_id}: {e}")
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE jobs SET status = 'FAILED' WHERE id = :jid"),
                        {"jid": job_id}
                    )
                return

        cli_cmd = [
            "python",
            "-m", "scripts.inference",
            "--unet_config_path", unet_config_path,
            "--inference_ckpt_path", inference_ckpt_path,
            "--inference_steps", str(inference_steps),
            "--guidance_scale", str(guidance_scale),
            "--audio_path", local_audio
        ]
        if local_video:
            cli_cmd.extend(["--video_path", local_video])
        local_output = os.path.join(working_dir, f"video_out_{job_id}.mp4")
        cli_cmd.extend(["--video_out_path", local_output])

        print(f"Running LatentSync CLI: {' '.join(cli_cmd)}")
        env = os.environ.copy()
        env["PYTHONPATH"] = "/app/LatentSync"
        completed = subprocess.run(
            cli_cmd,
            cwd="/app/LatentSync",
            capture_output=True,
            text=True,
            env=env
        )
        print(f"LatentSync stdout: {completed.stdout}")
        print(f"LatentSync stderr: {completed.stderr}")
        if completed.returncode != 0:
            print(f"Inference failed for job {job_id} with return code {completed.returncode}")
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE jobs SET status = 'FAILED' WHERE id = :jid"),
                    {"jid": job_id}
                )
            return

        output_bucket = "outputs"
        output_object = f"video_{job_id}_{uuid.uuid4().hex}.mp4"
        minio_path = upload_to_minio(local_output, output_bucket, output_object)

        with engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE jobs "
                    "SET status = 'COMPLETED', path_minio_video_output = :outpath "
                    "WHERE id = :jid"
                ),
                {"outpath": minio_path, "jid": job_id}
            )

        print(f"Job {job_id} completed, output: {minio_path}")

    finally:
        shutil.rmtree(working_dir, ignore_errors=True)

def background_video_watcher():
    print("ai_video: Background watcher thread started")
    while True:
        try:
            print("ai_video: Watcher loop alive")
            results = []
            with engine.connect() as conn:
                results = conn.execute(
                    text("SELECT id FROM jobs WHERE status = 'AUDIO_COMPLETE' AND path_minio_audio IS NOT NULL")
                ).fetchall()
                job_ids = [row[0] for row in results]
            if job_ids:
                print(f"ai_video: Found jobs to process: {job_ids}")
            else:
                print("ai_video: No AUDIO_COMPLETE jobs found")
            for job_id in job_ids:

                print(f"ai_video: Processing job {job_id} from watcher")
                process_job_from_db(
                    job_id,
                    "configs/unet/stage2.yaml",
                    "checkpoints/latentsync_unet.pt",
                    20,
                    2.0
                )
            time.sleep(10) 
        except Exception as e:
            print(f"ai_video: Exception in watcher loop: {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(10)

@app.on_event("startup")
def start_background_watcher():
    print("ai_video: Starting background watcher thread")
    t = threading.Thread(target=background_video_watcher, daemon=True)
    t.start()

@app.post("/process_video")
def process_video(
    job_id: int = Form(None),
    params: InferenceParams = Body(None)
):
    print(f"start of post process_video: job_id={job_id}, params={params}")

    if job_id is None and params is not None:
        job_id = params.job_id
    if job_id is None:
        raise HTTPException(status_code=422, detail="job_id is required")

    unet_config_path = params.unet_config_path if params else "configs/unet/stage2.yaml"
    inference_ckpt_path = params.inference_ckpt_path if params else "checkpoints/latentsync_unet.pt"
    inference_steps = params.inference_steps if params else 20
    guidance_scale = params.guidance_scale if params else 2.0

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT path_minio_audio, path_minio_video_input FROM jobs WHERE id = :jid"),
            {"jid": job_id}
        )
        job = result.fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        conn.execute(
            text("UPDATE jobs SET status = 'PROCESSING_VIDEO' WHERE id = :jid"),
            {"jid": job_id}
        )

    audio_minio_path, video_minio_path = job

    print(f"process_video: job_id={job_id}, audio_minio_path={audio_minio_path}, video_minio_path={video_minio_path}")

    if not audio_minio_path:
        raise HTTPException(status_code=400, detail=f"No audio path in job (job_id={job_id}). Job: {job}")

    working_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
    try:
        local_audio = os.path.join(working_dir, f"audio_{job_id}.wav")
        download_from_minio(audio_minio_path, local_audio)

        local_video = None
        if video_minio_path:
            local_video = os.path.join(working_dir, f"video_input_{job_id}.mp4")
            download_from_minio(video_minio_path, local_video)

        cli_cmd = [
            "python",
            "-m", "scripts.inference",
            "--unet_config_path", unet_config_path,
            "--inference_ckpt_path", inference_ckpt_path,
            "--inference_steps", str(inference_steps),
            "--guidance_scale", str(guidance_scale),
            "--audio_path", local_audio
        ]
        if local_video:
            cli_cmd.extend(["--video_path", local_video])
        local_output = os.path.join(working_dir, f"video_out_{job_id}.mp4")
        cli_cmd.extend(["--video_out_path", local_output])

        completed = subprocess.run(cli_cmd, cwd="/app/LatentSync", capture_output=True, text=True)
        if completed.returncode != 0:
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE jobs SET status = 'FAILED' WHERE id = :jid"),
                    {"jid": job_id}
                )
            raise HTTPException(
                status_code=500,
                detail=f"Inference failed: {completed.stderr}"
            )

        output_bucket = "outputs"
        output_object = f"video_{job_id}_{uuid.uuid4().hex}.mp4"
        minio_path = upload_to_minio(local_output, output_bucket, output_object)

        with engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE jobs "
                    "SET status = 'COMPLETED', path_minio_video_output = :outpath "
                    "WHERE id = :jid"
                ),
                {"outpath": minio_path, "jid": job_id}
            )

        return {"status": "success", "job_id": job_id, "path_minio_video_output": minio_path}

    finally:
        shutil.rmtree(working_dir, ignore_errors=True)

if __name__ == "__main__":
    print(f"Starting ai_video service...")
    import uvicorn
    uvicorn.run("process_video:app", host="0.0.0.0", port=8000, reload=False)
