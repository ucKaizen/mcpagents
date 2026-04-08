FROM python:3.12-slim

WORKDIR /app

# Install only the core dependencies (skip heavy SLM deps)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    "fastmcp>=0.1.3" \
    "openai>=1.40.0" \
    "python-dotenv>=1.0.1" \
    "fastapi>=0.111.0" \
    "uvicorn>=0.30.0" \
    "websockets>=12.0" \
    "pydantic>=2.7.0"

COPY server/ server/
COPY agent/ agent/
COPY web/ web/
COPY main.py .

EXPOSE 8001

CMD ["python", "main.py"]
