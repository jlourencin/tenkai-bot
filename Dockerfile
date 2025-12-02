# Imagem base Python
FROM python:3.11-slim

# Variável para evitar prompts
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Atualiza pacotes e instala dependências do Chromium/Playwright
RUN apt-get update && apt-get install -y \
    wget \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libxshmfence1 \
    fonts-liberation \
    libglib2.0-0 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Cria diretório da app
WORKDIR /app

# Copia arquivos
COPY requirements.txt .

# Instala libs Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Instala o Chromium do Playwright
RUN python -m playwright install chromium

# Copia o restante do projeto
COPY . .

# Porta padrão do Railway
ENV PORT=8080

# Comando para rodar a API Flask via Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
