FROM python:3.12-slim

WORKDIR /app

COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY web/ ./web/

ENV PYTHONUNBUFFERED=1
ENV API_HOST=0.0.0.0
ENV RENDER=true

WORKDIR /app/bot
CMD ["python", "main.py"]
