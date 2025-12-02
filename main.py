import os
import time
import json
import threading

import requests
from bs4 import BeautifulSoup
from flask import Flask

# ==========================
# VARIÁVEIS DE AMBIENTE
# ==========================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

PROXY_HOST = os.environ.get("PROXY_HOST", "").strip()
PROXY_PORT = os.environ.get("PROXY_PORT", "").strip()
PROXY_USER = os.environ.get("PROXY_USER", "").strip()
PROXY_PASS = os.environ.get("PROXY_PASS", "").strip()

_raw_players = os.environ.get("WATCHED_PLAYERS", "")

WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

ONLINE_URL = "https://ntotenkai.com.br/online"
CHECK_INTERVAL = 60  # segundos
STATE_FILE = "last_levels.json"

# ==========================
# CONFIG DO PROXY
# ==========================

def build_proxy_dict():
    if not (PROXY_HOST and PROXY_PORT and PROXY_USER and PROXY_PASS):
        print("[AVISO] Proxy não configurado completamente. Acesso direto será usado (pode dar 403).")
        return None

    proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
    print(f"[INFO] Usando proxy: {PROXY_HOST}:{PROXY_PORT}")
    return {
        "http": proxy_url,
        "https": proxy_url,
    }

PROXIES = build_proxy_dict()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
    "Connection": "close",
}

# ==========================
# FLASK (PARA O RAILWAY)
# ==========================

app = Flask(__name__)

@app.route("/")
def home():
    return (
        "✅ Bot de monitoramento com proxy residencial DataImpulse rodando!<br>"
        f"Jogadores monitorados: {', '.join(WATCHED_PLAYERS) or 'nenhum'}<br>"
        f"URL: {ONLINE_URL}<br>"
        f"Intervalo: {CHECK_INTERVAL}s<br>"
        f"Proxy configurado: {'sim' if PROXIES else 'não'}"
    )

@app.route("/health")
def health():
    return "OK", 200

# ==========================
# ESTADO DOS LEVELS
# ==========================

def load_last_levels():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERRO] Falha ao carregar {STATE_FILE}: {e}")
            return {}
    return {}

def save_last_levels(levels):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(levels, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {STATE_FILE}: {e}")

# ==========================
# DOWNLOAD HTML VIA PROXY
# ==========================

def fetch_html():
    try:
        print(f"[DEBUG] Acessando {ONLINE_URL}...")
        r = requests.get(
            ONLINE_URL,
            headers=HEADERS,
            proxies=PROXIES,
            timeout=30,
        )
        print(f"[DEBUG] Status HTTP: {r.status_code}")

        if r.status_code != 200:
            print(f"[ERRO] Status != 200. Status: {r.status_code}")
            # logar só o início do HTML pra debug
            preview = r.text[:200].replace("\n", " ")
            print(f"[DEBUG] Início do HTML: {preview}")
            return None

        return r.text

    except Exception as e:
        print(f"[ERRO] Falha ao buscar HTML: {e}")
        return None

# ==========================
# PARSER DA TABELA ONLINE
# ==========================

def parse_online_players(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    online = {}

    for row in rows:
        cols = row.find_all("td")
        # Estrutura esperada: # | outfit | name | level | vocation
        if len(cols) < 4:
            continue

        name = cols[2].get_text(strip=True)
        level_txt = cols[3].get_text(strip=True)

        if not name:
            continue
        if not level_txt.isdigit():
            continue

        level = int(level_txt)
        online[name] = level

    return online

# ==========================
# DISCORD
# ==========================

def send_embed(title, desc, color):
    if not DISCORD_WEBHOOK:
        print("[AVISO] DISCORD_WEBHOOK_URL não configurado, não enviarei webhook.")
        return

    payload = {"embeds": [{"title": title, "description": desc, "color": color}]}
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if r.status_code not in (200, 204):
            print(f"[ERRO] Webhook status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar webhook: {e}")

def send_up(player, old, new):
    send_embed("🚀 LEVEL UP", f"**{player}** subiu de {old} → {new}", 0x00FF00)

def send_down(player, old, new):
    send_embed("💀 LEVEL DOWN", f"**{player}** caiu de {old} → {new}", 0xFF0000)

# ==========================
# LOOP PRINCIPAL
# ==========================

def monitor():
    last = load_last_levels()
    print("▶ Bot iniciado!")
    print("Jogadores monitorados:", WATCHED_PLAYERS)

    while True:
        html = fetch_html()

        if not html:
            print("❌ HTML vazio ou erro na requisição. Tentando novamente depois...")
            time.sleep(CHECK_INTERVAL)
            continue

        online = parse_online_players(html)
        print("🔎 Players online encontrados:", list(online.keys()))

        for player in WATCHED_PLAYERS:
            current = online.get(player)
            old = last.get(player)

            if current is None:
                print(f"❌ {player} está offline ou não foi encontrado na lista.")
                continue

            if old is None:
                print(f"📌 Primeiro registro de {player}: {current}")
                last[player] = current

            elif current > old:
                print(f"🔥 UP: {player} {old} → {current}")
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

# ==========================
# MAIN
# ==========================

if __name__ == "__main__":
    # Thread do monitor
    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    # Flask para Railway
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
