FROM python:3.9-slim

# FFmpeg kurulumu
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Gerekli dosyaları kopyala
COPY requirements.txt .
COPY bot.py .

# Python bağımlılıklarını yükle
RUN pip install --no-cache-dir -r requirements.txt

# downloads klasörünü oluştur
RUN mkdir downloads

CMD ["python", "bot.py"] 