FROM python:3.11-slim

WORKDIR /app

# Wycisz debconf – Docker nie ma TTY, więc dialog zawsze pada na Noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Zależności systemowe
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
