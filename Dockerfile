FROM python:3.10-slim

# Instala dependências necessárias do Playwright
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

# Instalar Playwright
RUN pip install playwright
RUN playwright install chromium

# Copiar projeto
WORKDIR /app
COPY . .

# Instalar requirements.txt
RUN pip install -r requirements.txt

# Expor porta 8080
EXPOSE 8080

CMD ["python", "main.py"]
