FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/certs

EXPOSE 9000 8000 8888 5001

CMD ["python", "manage.py", "runserver_plus", "0.0.0.0:9000", "--cert-file", "/app/certs/cert.pem", "--key-file", "/app/certs/key.pem"]
