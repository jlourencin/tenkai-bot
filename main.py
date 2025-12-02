import os
import time
import json
import threading
import re

import requests
import cloudscraper
from bs4 import BeautifulSoup
from flask import Flask

# ======================
# VARIÁVEIS DE AMBIENTE
# ======================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
_raw_players = os.environ.get("WATCHED_PLAYERS", "")

WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

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
        "✅ Bot CLOUDSCRAPER rodando!<br>"
        f"Jogadores monitorados: {', '.join(WATCHED_PLAYERS) or 'nenhum'}<br>"
        f"Página de online: {ONLINE_URL}<br>"
        f"Intervalo: {CHECK_INTERVAL}s"
    )

# ======================
# ESTADO
# ======================

def load_last_levels():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_last_levels(d):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

# ======================
# BYPASS CLOUDFLARE (CLOUDSCRAPER)
# ======================

scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False
    }
)

def fetch_online_html():
    try:
        print(f"[DEBUG] Acessando {ONLINE_URL} com CloudScraper...")
        r = scraper.get(ONLINE_URL, timeout=30)

        if r.status_code != 200:
            print(f"[ERRO] Status {r.status_code}")
            return None

        html = r.text

        if "Just a moment" in html or "cf-browser-verification" in html:
            print("❌ Cloudflare bloqueou. Tentando headers extras...")
            r = scraper.get(ONLINE_URL, timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36"
                }
            )
            html = r.text

        return html

    except Exception as e:
        print(f"[ERRO] CloudScraper: {e}")
        return None

# ======================
# PARSER
# ======================

def parse_online_players(html):
    soup = BeautifulSoup(html, "html.parser")
    online = {}

    tables = soup.find_all("table")
    if not tables:
        print("[WARN] Nenhuma tabela encontrada.")
        return online

    target = None
    for t in tables:
        if any(x in t.get_text() for x in ["Players Online", "Vocation", "Level"]):
            target = t
            break

    if not target:
        print("[WARN] Nenhuma tabela válida encontrada.")
        return online

    for row in target.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        name = cols[2].get_text(strip=True)
        lvl = cols[3].get_text(strip=True)

        m = re.search(r"\d+", lvl)
        if not name or not m:
            continue

        online[name] = int(m.group(0))

    return online

# ======================
# DISCORD
# ======================

def send_up(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    requests.post(DISCORD_WEBHOOK, json={
        "embeds": [{
            "title": "⚡ UP!",
            "description": f"{player} subiu de {old} → {new}",
            "color": 0x00FF00
        }]
    })

def send_down(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    requests.post(DISCORD_WEBHOOK, json={
        "embeds": [{
            "title": "💀 DOWN!",
            "description": f"{player} caiu de {old} → {new}",
            "color": 0xFF0000
        }]
    })

# ======================
# LOOP
# ======================

def monitor():
    last = load_last_levels()
    print("▶ Bot CloudScraper iniciado!")
    print("Jogadores monitorados:", WATCHED_PLAYERS)

    while True:
        html = fetch_online_html()

        if not html:
            print("❌ HTML vazio, tentando de novo...")
            time.sleep(CHECK_INTERVAL)
            continue

        online = parse_online_players(html)
        print("🔎 Players online encontrados:", list(online.keys()))

        for p in WATCHED_PLAYERS:
            current = online.get(p)
            old = last.get(p)

            if current is None:
                print(f"❌ {p} OFFLINE")
                continue

            if old is None:
                print(f"📍 Primeiro registro: {p} = {current}")
                last[p] = current
            elif current > old:
                print(f"⚡ UP {p}: {old} → {current}")
                send_up(p, old, current)
                last[p] = current
            elif current < old:
                print(f"💀 DOWN {p}: {old} → {current}")
                send_down(p, old, current)
                last[p] = current
            else:
                print(f"✔ {p}: {current}")

        save_last_levels(last)
        print(f"⏳ Aguardando {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)

# ======================
# MAIN
# ======================

if __name__ == "__main__":
    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
