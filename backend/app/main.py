# app/main.py

import os
import uuid
import pika
import shutil
import tempfile
from io import BytesIO

from fastapi import FastAPI, HTTPException, status, UploadFile, File, Form, Depends, Request
import logging
from sqlalchemy.orm import Session

from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

from . import models, schemas, database

load_dotenv()

app = FastAPI()
database.Base.metadata.create_all(bind=database.engine)


minio_client = Minio(
    os.getenv("MINIO_URL", "minio:9000").replace("http://", "").replace("https://", ""),
    access_key=os.getenv("MINIO_ACCESS_KEY", "minio"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minio123"),
    secure=False
)

for bucket in ["texts", "audios", "videos"]:
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def publish_job(job_id: int):
    connection = pika.BlockingConnection(
        pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"))
    )
    channel = connection.channel()
    channel.queue_declare(queue='job_queue')
    channel.basic_publish(
        exchange='',
        routing_key='job_queue',
        body=str(job_id)
    )
    connection.close()

@app.post(
    "/jobs/",
    response_model=schemas.JobResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_job(
    request: Request,
    text_content: str = Form(None),        
    audio_file: UploadFile = File(None),  
    video_file: UploadFile = File(None), 
    db: Session = Depends(get_db)
):

    logging.info(f"Headers: {request.headers}")
    logging.info(f"Content-Type: {request.headers.get('content-type')}")

    if not text_content and not audio_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of text or audio must be provided"
        )

    text_path = None
    if text_content:
        text_filename = f"text-{uuid.uuid4()}.txt"
        text_path = f"texts/{text_filename}"

        minio_client.put_object(
            "texts",
            text_filename,
            BytesIO(text_content.encode("utf-8")),
            len(text_content.encode("utf-8"))
        )

    audio_input_path = None
    if audio_file:
        ext = os.path.splitext(audio_file.filename)[1]
        audio_filename = f"audio-input-{uuid.uuid4()}{ext}"
        audio_input_path = f"audios/{audio_filename}"
        audio_data = await audio_file.read()
        minio_client.put_object(
            "audios",
            audio_filename,
            BytesIO(audio_data),
            len(audio_data)
        )

    video_input_path = None
    if video_file:
        ext = os.path.splitext(video_file.filename)[1]
        video_filename = f"video-input-{uuid.uuid4()}{ext}"
        video_input_path = f"videos/{video_filename}"
        video_data = await video_file.read()
        minio_client.put_object(
            "videos",
            video_filename,
            BytesIO(video_data),  
            len(video_data)
        )

    db_job = models.Job(
        path_minio_text=text_path,
        path_minio_audio_input=audio_input_path,
        path_minio_video_input=video_input_path
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    if db_job.updated_at is None:
        db_job.updated_at = db_job.created_at

    logging.info(f"Publishing job {db_job.id} to RabbitMQ")
    publish_job(db_job.id)
    return db_job

@app.get(
    "/jobs/{job_id}",
    response_model=schemas.JobResponse
)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.updated_at is None:
        job.updated_at = job.created_at
    return job
