from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobCreate(BaseModel):
    text_content: str

class JobResponse(BaseModel):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    path_minio_text: Optional[str]
    path_minio_audio: Optional[str]
    path_minio_video_input: Optional[str]
    path_minio_video_output: Optional[str]

    class Config:
        orm_mode = True