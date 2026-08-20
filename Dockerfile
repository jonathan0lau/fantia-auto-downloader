FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tokyo

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY fantia_downloader.py ./

ENTRYPOINT ["python", "/app/fantia_downloader.py"]
CMD ["--config", "/config/config.json", "--download-root", "/downloads", "--schedule", "03:00"]
