FROM python:3.13-slim

# Install OS dependencies and Tesseract OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libheif-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=2.1.2
RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app

# Copy poetry files first for better caching
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no venv — Render prefers system Python)
RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-root

# Copy the actual app code
COPY src ./src

# Add src to PYTHONPATH so python can find the module
ENV PYTHONPATH="/app/src"

# Expose port for Render
EXPOSE 10827

# Start FastAPI
CMD ["uvicorn", "simsim_tools_server.main:app", "--host", "0.0.0.0", "--port", "10827"]
# CMD uvicorn simsim_tools_server.main:app --host 0.0.0.0 --port ${PORT:-10827}