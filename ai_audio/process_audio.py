import os
import uuid
import torch
from fastapi import FastAPI, HTTPException, Form, Body
from minio import Minio
from minio.error import S3Error
from sqlalchemy import create_engine, text
import requests
from dotenv import load_dotenv
from chatterbox.tts import ChatterboxTTS
import torchaudio as ta
import librosa
import soundfile as sf
import tempfile

load_dotenv()
app = FastAPI()


minio_url = os.getenv("MINIO_URL", "minio:9000").replace("http://", "").replace("https://", "")

minio_client = Minio(
    minio_url,
    access_key=os.getenv("MINIO_ACCESS_KEY", "minio"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minio123"),
    secure=False
)

DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://root:admin@postgres:5432/pgdb")
engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
if DATABASE_URL:
    print(f"Connecting to database at {DATABASE_URL}")

print("Loading ChatterboxTTS model...")
model = ChatterboxTTS.from_pretrained(device="cuda")
print("ChatterboxTTS model loaded.")


def file_exists(key):
    try:
        minio_client.stat_object("audios", key)
        return True
    except S3Error as e:
        if e.code == "NoSuchKey":
            return False
        else:
            raise



@app.post("/process_audio")
def process_audio(
    job_id: int = Form(None), 
    job_id_json: dict = Body(None)
):

    if job_id is None and job_id_json is not None:
        job_id = job_id_json.get("job_id")
    if job_id is None:
        raise HTTPException(status_code=422, detail="job_id is required")
    


    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT path_minio_text, path_minio_audio_input FROM jobs WHERE id = :job_id"),
            {"job_id": job_id}
        )
        job = result.fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")


        conn.execute(
            text("UPDATE jobs SET status = 'PROCESSING_AUDIO' WHERE id = :job_id"),
            {"job_id": job_id}
        )

    text_content = None
    if job[0]:
        bucket, object_path = job[0].split('/', 1)
        try:
            response = minio_client.get_object(bucket, object_path)
            text_content = response.data.decode('utf-8')
            response.close()
            response.release_conn()
        except S3Error as e:
            print(f"Error getting text: {e}")
    

    audio_input = None
    if job[1]:
        bucket, object_path = job[1].split('/', 1)
        try:
            response = minio_client.get_object(bucket, object_path)
            audio_input = response.data
            response.close()
            response.release_conn()
        except S3Error as e:
            print(f"Error getting audio input: {e}")
    
    # Validate inputs
    if not text_content and not audio_input:
        return {"status": "error", "message": "No inputs provided"}
    
    try:

        output_audio = model.generate(text_content)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            tmp_wav_path = tmpfile.name

        if isinstance(output_audio, torch.Tensor):
            ta.save(tmp_wav_path, output_audio.cpu(), 24000) 
        else:
            sf.write(tmp_wav_path, output_audio, 24000)
        print(f"Uploading audio to MinIO: {tmp_wav_path}, size: {os.path.getsize(tmp_wav_path)} bytes")
        audio_filename = f"audio-{uuid.uuid4()}.wav"
        audio_path = f"audios/{audio_filename}" 
        assert not audio_filename.endswith('/')
        with open(tmp_wav_path, "rb") as f: 
            minio_client.put_object(
                "audios", audio_filename, f, os.path.getsize(tmp_wav_path))
        os.remove(tmp_wav_path)
        
        try:
            with engine.connect() as conn:
                print(f"Updating job {job_id} status to AUDIO_COMPLETE")
                conn.execute(
                    text("UPDATE jobs SET status = 'AUDIO_COMPLETE', path_minio_audio = :audio_path WHERE id = :job_id"),
                    {"audio_path": audio_path, "job_id": job_id}
                )
                result = conn.execute(
                    text("SELECT status, path_minio_audio FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id}
                ).fetchone()
                print(f"DB after update for job {job_id}: {result}")
                print(file_exists(audio_path))

        except Exception as e:
            print(f"Failed to update job {job_id} to AUDIO_COMPLETE: {e}")

        return {"status": "success", "job_id": job_id}
    
    except Exception as e:
        print(f"Audio processing failed: {e}")
        """with engine.connect() as conn:
            conn.execute(
                text("UPDATE jobs SET status = 'FAILED' WHERE id = :job_id"),
                {"job_id": job_id}
            )
        """
        return {"status": "error", "message": str(e)}
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)