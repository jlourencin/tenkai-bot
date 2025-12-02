from flask import Flask
import threading
import time
import requests
from bs4 import BeautifulSoup
import os
import json

# === CONFIGURAÇÕES ===
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")  # webhook do Discord

# WATCHED_PLAYERS via variável de ambiente:
# Ex: WATCHED_PLAYERS="Joao, Maria;Jose"
raw_players = os.environ.get("WATCHED_PLAYERS", "")
WATCHED_PLAYERS = [
    p.strip() for p in raw_players.replace(";", ",").split(",") if p.strip()
]

CHECK_INTERVAL = 60  # intervalo de checagem em segundos
MIN_LEVEL = 690      # nível mínimo para considerar up/morte

STATE_FILE = "last_levels.json"

# === SERVIDOR FLASK PARA MANTER ONLINE ===
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Tenkai está rodando!", 200

# === FUNÇÕES ===

def get_online_players():
    url = "https://ntotenkai.com.br/online"
    headers = {
        # User-Agent de navegador real
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://ntotenkai.com.br/",
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] Status ao acessar /online: {r.status_code}")

        if r.status_code == 403:
            print("[ERRO] 403 Forbidden: o servidor está bloqueando a requisição do bot.")
            return []

        r.raise_for_status()
    except Exception as e:
        print(f"[ERRO] Falha ao acessar o site: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    players = []

    for row in soup.select("tr"):
        cols = row.find_all("td")
        if len(cols) >= 2 and cols[1].text.strip().isdigit():
            name = cols[0].text.strip()
            level = int(cols[1].text.strip())
            players.append((name, level))

    return players


def send_embed_to_discord(jogador, old_level, new_level):
    embed = {
        "title": "☠️ UPOU PARA MORRER",
        "description": f"**{jogador}** subiu de nível e já vai morrer kkkk xd ☠️🔪",
        "color": 0x00FF00,
        "fields": [
            {"name": "💩 Jogador", "value": jogador, "inline": True},
            {"name": "📈 Level", "value": f"{old_level} → {new_level}", "inline": True},
        ],
        "footer": {"text": "🔥 JOHTTO HACKER DEUS"},
    }
    payload = {"embeds": [embed]}

    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if response.status_code not in [200, 204]:
            print(f"[ERRO] Webhook falhou com status {response.status_code}")
            print(f"[RESPOSTA] {response.text}")
        else:
            print("[OK] Mensagem de UP enviada ao Discord.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar embed de UP: {e}")


def send_death_embed_to_discord(jogador, old_level, new_level):
    embed = {
        "title": "💀 XIIII MORREU NOOB",
        "description": f"☠️ **{jogador}** já morreu noobasso",
        "color": 0xFF0000,
        "fields": [
            {"name": "💩 Jogador", "value": jogador, "inline": True},
            {"name": "📉 Level", "value": f"{o
