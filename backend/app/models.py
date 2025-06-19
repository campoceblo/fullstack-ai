from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from .database import Base

class JobStatus:
    SUBMITTED = "SUBMITTED"
    PROCESSING_AUDIO = "PROCESSING_AUDIO"
    AUDIO_COMPLETE = "AUDIO_COMPLETE"
    PROCESSING_VIDEO = "PROCESSING_VIDEO"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default=JobStatus.SUBMITTED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    path_minio_text = Column(String)
    path_minio_audio_input = Column(String)  
    path_minio_audio = Column(String)       
    path_minio_video_input = Column(String)  
    path_minio_video_output = Column(String)