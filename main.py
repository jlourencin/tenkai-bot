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

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
_raw_players = os.environ.get("WATCHED_PLAYERS", "")

WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

if not WATCHED_PLAYERS:
    print("[AVISO] WATCHED_PLAYERS não configurado ou vazio.")

if not DISCORD_WEBHOOK:
    print("[AVISO] DISCORD_WEBHOOK_URL não configurado. Não será possível enviar embeds.")

# ======================
# CONFIGURAÇÃO DO SITE
# ======================
ONLINE_URL = "https://ntotenkai.com.br/online"

CHECK_INTERVAL = 60  # segundos
STATE_FILE = "last_levels.json"

# ======================
# FLASK
# ======================

app = Flask(__name__)

@app.route("/")
def home():
    return (
        "✅ Bot Playwright (online page) rodando!<br>"
        f"Jogadores monitorados: {', '.join(WATCHED_PLAYERS) or 'nenhum'}<br>"
        f"Página de online: {ONLINE_URL}<br>"
        f"Intervalo: {CHECK_INTERVAL}s"
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
        except Exception:
            return {}
    return {}

def save_last_levels(levels):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(levels, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {STATE_FILE}: {e}")

# ======================
# PLAYWRIGHT → HTML
# ======================

def fetch_online_html() -> str | None:
    """
    Abre a página de online em um navegador headless (Chromium via Playwright)
    e retorna o HTML.
    """
    print(f"[DEBUG] Abrindo página de online: {ONLINE_URL}")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()
            page.goto(
                ONLINE_URL,
                timeout=60000,
                wait_until="domcontentloaded",
            )
            # pequena espera pra garantir que carregou tudo
            page.wait_for_timeout(2000)
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
    Lê a tabela 'Players Online' do site.

    Estrutura das colunas:
    # | Outfit | Name | Level | Vocation

    Retorna:
      { "Nome do Player": level_int, ... }
    """
    soup = BeautifulSoup(html, "html.parser")
    online = {}

    # tenta achar a tabela que contém o texto "Players Online"
    table = None
    for t in soup.find_all("table"):
        if "Players Online" in t.get_text():
            table = t
            break
    if table is None:
        # fallback: primeira tabela da página
        table = soup.find("table")

    if table is None:
        print("[WARN] Nenhuma tabela encontrada no HTML.")
        return online

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        # precisa ter pelo menos: #, outfit, name, level
        if len(cols) < 4:
            continue

        # 3ª coluna = Name (índice 2), geralmente dentro de <a>
        name_el = cols[2].find("a") or cols[2]
        name = name_el.get_text(strip=True)

        # 4ª coluna = Level (índice 3)
        lvl_txt = cols[3].get_text(" ", strip=True)
        m = re.search(r"\d+", lvl_txt)
        if not name or not m:
            continue

        level = int(m.group(0))
        online[name] = level

    return online


# ======================
# DISCORD
# ======================

def send_up(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    embed = {
        "title": "☠️ UPOU PARA MORRER",
        "description": f"**{player}** subiu de nível!",
        "color": 0x00FF00,
        "fields": [
            {"name": "Jogador", "value": player, "inline": True},
            {"name": "Level", "value": f"{old} → {new}", "inline": True},
        ],
    }
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
        if r.status_code not in (200, 204):
            print(f"[ERRO] Webhook UP status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar embed de UP: {e}")

def send_down(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    embed = {
        "title": "💀 XIIII MORREU NOOB",
        "description": f"**{player}** perdeu level!",
        "color": 0xFF0000,
        "fields": [
            {"name": "Jogador", "value": player, "inline": True},
            {"name": "Level", "value": f"{old} → {new}", "inline": True},
        ],
    }
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
        if r.status_code not in (200, 204):
            print(f"[ERRO] Webhook DOWN status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar embed de DOWN: {e}")

# ======================
# LOOP DO BOT
# ======================

def monitor():
    last = load_last_levels()
    print("▶ Bot Playwright + Online Page iniciado!")
    print("Jogadores monitorados:", WATCHED_PLAYERS)
    print("ONLINE_URL:", ONLINE_URL)

    while True:
        html = fetch_online_html()
        if html is None:
            print("❌ Não consegui abrir a página de online.")
            time.sleep(CHECK_INTERVAL)
            continue

        online = parse_online_players(html)
        print("🔎 Players online encontrados:", list(online.keys()))

        for player in WATCHED_PLAYERS:
            current = online.get(player)
            old = last.get(player)

            if current is None:
                print(f"❌ {player} está offline ou não está na lista de online.")
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
    # Thread do bot
    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    # Flask para Railway
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
