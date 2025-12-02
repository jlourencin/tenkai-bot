import os
import time
import json
import threading
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask
from playwright.sync_api import sync_playwright

# ======================
# VARIÁVEIS DE AMBIENTE
# ======================
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
_raw_players = os.environ.get("WATCHED_PLAYERS", "")

WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

# ======================
# CONFIGURAÇÃO DO SITE
# ======================
# 👉 TROQUE SOMENTE ISTO
ONLINE_URL = "https://ntotenkai.com.br/online"

CHECK_INTERVAL = 60
STATE_FILE = "last_levels.json"

# ======================
# FLASK
# ======================
app = Flask(__name__)

@app.route("/")
def home():
    return (
        "✅ Bot Playwright (online page) rodando!<br>"
        f"Jogadores monitorados: {', '.join(WATCHED_PLAYERS)}<br>"
        f"Página de online: {ONLINE_URL}"
    )

@app.route("/health")
def health():
    return "OK", 200

# ======================
# ESTADO
# ======================

def load_last_levels():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_last_levels(levels):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(levels, f, indent=2, ensure_ascii=False)

# ======================
# PLAYWRIGHT → HTML
# ======================

def fetch_online_html() -> str | None:
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(ONLINE_URL, timeout=30000, wait_until="networkidle")
            html = page.content()
            browser.close()
            return html

    except Exception as e:
        print(f"[ERRO] Falha Playwright ao abrir ONLINE_URL: {e}")
        return None

# ======================
# PARSER → TABELA DE ONLINE
# ======================

def parse_online_players(html: str) -> dict:
    """
    Retorna dict no formato:
    {
        "Alienwarre": 527,
        "Zeus": 480,
        ...
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    online = {}

    # Procura tabelas e linhas
    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        name = cols[0].get_text(strip=True)
        lvl_txt = cols[1].get_text(strip=True)

        if not re.match(r"^\d+$", lvl_txt):
            continue

        level = int(lvl_txt)
        online[name] = level

    return online

# ======================
# DISCORD
# ======================

def send_up(p, old, new):
    embed = {
        "title": "☠️ UPOU PARA MORRER",
        "description": f"**{p}** subiu de nível!",
        "color": 0x00FF00,
        "fields": [
            {"name": "Jogador", "value": p, "inline": True},
            {"name": "Level", "value": f"{old} → {new}", "inline": True},
        ]
    }
    requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})

def send_down(p, old, new):
    embed = {
        "title": "💀 XIIII MORREU NOOB",
        "description": f"**{p}** perdeu level!",
        "color": 0xFF0000,
        "fields": [
            {"name": "Jogador", "value": p, "inline": True},
            {"name": "Level", "value": f"{old} → {new}", "inline": True},
        ]
    }
    requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})

# ======================
# BOT LOOP
# ======================

def monitor():
    last = load_last_levels()
    print("▶ Bot Playwright + Online Page iniciado!")

    while True:
        html = fetch_online_html()
        if html is None:
            print("❌ Não consegui abrir a página de online.")
            time.sleep(CHECK_INTERVAL)
            continue

        online = parse_online_players(html)
        print("🔎 Players online:", list(online.keys()))

        for player in WATCHED_PLAYERS:
            current = online.get(player)
            old = last.get(player)

            if current is None:
                print(f"❌ {player} está offline.")
                continue

            if old is None:
                print(f"📌 Primeiro registro: {player} = {current}")
                last[player] = current

            elif current > old:
                print(f"🚀 UP: {player} {old} → {current}")
                send_up(player, old, current)
                last[player] = current

            elif current < old:
                print(f"💀 DOWN: {player} {old} → {current}")
                send_down(player, old, current)
                last[player] = current

            else:
                print(f"✔ {player}: {current}")

        save_last_levels(last)
        print(f"⏳ Aguardando {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)

# ======================
# MAIN
# ======================

if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
