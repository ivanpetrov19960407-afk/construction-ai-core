# Stage 1: builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --prefix=/install \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "langgraph>=0.2.0" \
    "langchain-openai>=0.2.0" \
    "langchain-community>=0.3.0" \
    "httpx>=0.27.0" \
    "aiogram>=3.13.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.5.0" \
    "python-multipart>=0.0.9" \
    "python-dotenv>=1.0.0" \
    "docxtpl>=0.18.0" \
    "python-docx>=1.1.0" \
    "docx2pdf>=0.1.8" \
    "weasyprint>=62.0" \
    "pdfplumber>=0.11.0" \
    "chromadb>=0.5.0" \
    "sentence-transformers>=3.0.0" \
    "aiosqlite>=0.20.0" \
    "slowapi>=0.1.9" \
    "structlog>=24.0.0" \
    "tqdm>=4.66.0" \
    "prometheus-fastapi-instrumentator>=7.0.0" \
    "boto3>=1.34.0"

# Stage 2: runtime
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

RUN python scripts/generate_templates.py
RUN mkdir -p data/chroma data/db templates

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
