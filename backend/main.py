import os, uuid
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from redis import Redis
from rq import Queue
import boto3

app = FastAPI()
# Redis queue
redis_url = os.getenv("REDIS_URL")
q = Queue(connection=Redis.from_url(redis_url))
# MinIO/S3 client
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("MINIO_URL"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
)

BUCKET = "tasks"
# ensure bucket exists
try:
    s3.create_bucket(Bucket=BUCKET)
except:
    pass

@app.get("/", response_class=HTMLResponse)
async def form():
    html = """
    <h1>Submit TTS Job</h1>
    <form action="/submit" enctype="multipart/form-data" method="post">
      Text: <input type="text" name="text"><br><br>
      Audio: <input type="file" name="audio"><br><br>
      <button type="submit">Submit</button>
    </form>
    """
    return html

@app.post("/submit")
async def submit(text: str = Form(...), audio: UploadFile = None):
    job_id = str(uuid.uuid4())
    # Upload inputs to S3
    s3.upload_fileobj(audio.file, BUCKET, f"{job_id}/audio")
    s3.put_object(Bucket=BUCKET, Key=f"{job_id}/text", Body=text.encode())
    # Enqueue worker job
    q.enqueue("worker.process_job", job_id)
    return {"job_id": job_id}


@app.get("/result/{job_id}")
def get_result(job_id: str):
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=f"{job_id}/output.mp3")
        file_stream = io.BytesIO(obj["Body"].read())

        return StreamingResponse(
            file_stream,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="{job_id}_output.mp3"'
             }
         )
    except:
        raise HTTPException(status_code=404, detail="Result not found")
