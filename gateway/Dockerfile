FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir \
    "openai>=1.40.0" \
    "fastapi>=0.111.0" \
    "uvicorn>=0.30.0" \
    "websockets>=12.0" \
    "pydantic>=2.7.0" \
    "httpx>=0.27.0"

COPY gateway/app.py gateway/app.py
COPY web/ web/

EXPOSE 8000
CMD ["python", "gateway/app.py"]
