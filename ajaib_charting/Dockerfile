FROM python:3.10-slim

# Set timezone ke Jakarta
ENV TZ=Asia/Jakarta
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install git (dibutuhkan untuk install tvdatafeed dari github)
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY bot_telegram.py .
COPY watchlist.json .

# Jalankan bot (dengan flag -u agar log muncul realtime di Dokploy)
CMD ["python", "-u", "bot_telegram.py"]
