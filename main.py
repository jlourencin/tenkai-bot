import os
import time
import json
import threading
import re
import random
import subprocess

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
            return json.load(open(STATE_FILE, "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_last_levels(d):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {STATE_FILE}: {e}")

# ============================
# PLAYWRIGHT BYPASS CLOUDFLARE
# ============================

def _install_webkit():
    """Instala o navegador WebKit se ainda não existir."""
    print("[INFO] WebKit não encontrado. Executando 'playwright install webkit'...")
    try:
        # check=False pra não quebrar o processo se der algum warning
        subprocess.run(["playwright", "install", "webkit"], check=True)
        print("[INFO] WebKit instalado com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao instalar WebKit: {e}")

def fetch_online_html(_retry=False):
    """
    Abre a página de online em um navegador headless (WebKit via Playwright)
    e retorna o HTML. Se o executável não existir, instala automaticamente.
    """
    print(f"[DEBUG] Abrindo página (WebKit stealth): {ONLINE_URL}")

    try:
        with sync_playwright() as pw:
            # WEBKIT — menos detectado que Chromium
            browser = pw.webkit.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-web-security",
                ]
            )

            # CONTEXTO COM SPOOFING REAL
            context = browser.new_context(
                user_agent=(
                    f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_{random.randint(1,9)}) "
                    f"AppleWebKit/605.1.{random.randint(1,40)} (KHTML, like Gecko) "
                    f"Version/{random.randint(12,16)}.1 Safari/605.1.{random.randint(1,40)}"
                ),
                locale="en-US",
                timezone_id="America/Sao_Paulo",
                permissions=[],
                viewport={"width": random.randint(1100,1400), "height": random.randint(700,900)},
            )

            page = context.new_page()

            page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            })

            # TENTA ATÉ PASSAR DO CLOUDFLARE
            for attempt in range(5):
                print(f"[DEBUG] Tentativa {attempt+1}/5")
                page.goto(ONLINE_URL, wait_until="domcontentloaded", timeout=60000)
                content = page.content()

                if "Just a moment" not in content and "cf-browser-verification" not in content:
                    break

                print("[DEBUG] Cloudflare detectou bot. Tentando novamente...")
                time.sleep(2)

            browser_html = page.content()
            browser.close()
            return browser_html

    except Exception as e:
        msg = str(e)
        # Erro clássico de navegador não instalado
        if ("Executable doesn't exist" in msg or "playwright install" in msg) and not _retry:
            _install_webkit()
            # tenta mais uma vez
            return fetch_online_html(_retry=True)

        print(f"[ERRO] Playwright CF bypass: {e}")
        return None

# ============================
# PARSER DA TABELA
# ============================

def parse_online_players(html):
    """
    Lê a tabela 'Players Online' do site.

    Estrutura das colunas:
    # | Outfit | Name | Level | Vocation

    Retorna:
      { "Nome do Player": level_int, ... }
    """
    soup = BeautifulSoup(html, "html.parser")
    online = {}

    tables = soup.find_all("table")
    if not tables:
        print("[WARN] Nenhuma tabela encontrada no HTML.")
        return online

    # acha a tabela certa
    target = None    # tabela com os headers que a gente quer
    for tb in tables:
        if any(x in tb.get_text() for x in ["Players Online", "Level", "Vocation"]):
            target = tb
            break

    if not target:
        print("[WARN] Nenhuma tabela válida encontrada.")
        return online

    for row in target.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        name_el = cols[2].find("a") or cols[2]
        name = name_el.get_text(strip=True)

        lvl_text = cols[3].get_text(strip=True)
        m = re.search(r"\d+", lvl_text)
        if not name or not m:
            continue

        online[name] = int(m.group(0))

    return online

# ============================
# NOTIFICAÇÕES
# ============================

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
        requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print(f"[ERRO] Webhook UP: {e}")

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
        requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print(f"[ERRO] Webhook DOWN: {e}")

# ============================
# LOOP PRINCIPAL
# ============================

def monitor():
    last = load_last_levels()
    print("▶ Bot Playwright + Online Page iniciado!")
    print("Jogadores monitorados:", WATCHED_PLAYERS)
    print("ONLINE_URL:", ONLINE_URL)

    while True:
        html = fetch_online_html()
        if not html:
            print("❌ HTML vazio, tentando novamente...")
            time.sleep(CHECK_INTERVAL)
            continue

        online = parse_online_players(html)
        print("🔎 Players online encontrados:", list(online.keys()))

        for p in WATCHED_PLAYERS:
            current = online.get(p)
            old = last.get(p)

            if current is None:
                print(f"❌ {p} está offline ou não está na lista de online.")
                continue

            if old is None:
                print(f"📌 Primeiro registro: {p} = {current}")
                last[p] = current
            elif current > old:
                print(f"🚀 UP: {p} {old} → {current}")
                send_up(p, old, current)
                last[p] = current
            elif current < old:
                print(f"💀 DOWN: {p} {old} → {current}")
                send_down(p, old, current)
                last[p] = current
            else:
                print(f"✔ {p}: {current}")

        save_last_levels(last)
        print(f"⏳ Aguardando {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)

# ============================
# MAIN
# ============================

if __name__ == "__main__":
    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
