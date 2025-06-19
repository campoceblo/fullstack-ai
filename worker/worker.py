import os
import pika
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import socket 

load_dotenv()

DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://root:admin@postgres:5432/pgdb")
engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def process_job(job_id):

    with SessionLocal() as db:
        db.execute(
            text("UPDATE jobs SET status = 'PROCESSING_AUDIO' WHERE id = :job_id"),
            {"job_id": job_id}
        )

    audio_service_url = "http://ai_audio:8000/process_audio"
    print(f"Worker: Sending job {job_id} to ai_audio")
    response_audio = requests.post(audio_service_url, data={"job_id": job_id})
    print(f"Worker: ai_audio response {response_audio.status_code} {response_audio.text}")

    return response_audio.status_code == 200

def callback(ch, method, properties, body):
    job_id = int(body)
    print(f"Received job: {job_id}")
    success = process_job(job_id)
    ch.basic_ack(delivery_tag=method.delivery_tag)
    if success:
        print(f"Job {job_id} sent to ai_audio successfully")
    else:
        print(f"Job {job_id} failed to send to ai_audio")

def main():
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    print(f"Connecting to RabbitMQ at {rabbitmq_url} ...")


    for _ in range(10):
        try:
            params = pika.URLParameters(rabbitmq_url)
            params.heartbeat = 600  
            connection = pika.BlockingConnection(params)
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"Waiting for RabbitMQ to be ready at {rabbitmq_url} ...")
            import time
            time.sleep(3)
        except Exception as e:
            print(f"Error connecting to RabbitMQ at {rabbitmq_url}: {e}")
            import time
            time.sleep(3)
    else:
        print(f"Failed to connect to RabbitMQ at {rabbitmq_url} after multiple attempts.")
        return

    channel = connection.channel()
    channel.queue_declare(queue='job_queue')
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='job_queue', on_message_callback=callback)
    print("Worker started. Waiting for jobs...")
    channel.start_consuming()

if __name__ == "__main__":
    main()
