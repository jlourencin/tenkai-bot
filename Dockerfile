FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Dependências necessárias pro Chromium/Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libxshmfence1 \
    fonts-liberation \
    libglib2.0-0 \
    libgdk-pixbuf-2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# instala libs Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# instala o navegador Chromium do Playwright
RUN python -m playwright install chromium

# copia o resto do projeto
COPY . .

EXPOSE 8080

CMD ["python", "main.py"]
