import os
import time
import json
import threading
import re
import random

import requests
from bs4 import BeautifulSoup
from flask import Flask
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
_raw_players = os.environ.get("WATCHED_PLAYERS", "")

WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

ONLINE_URL = "https://ntotenkai.com.br/online"
CHECK_INTERVAL = 60
STATE_FILE = "last_levels.json"

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot ativo!"

def load_last_levels():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, "r", encoding="utf-8"))
        except:
            return {}
    return {}

def save_last_levels(d):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

# ============================
# PLAYWRIGHT BYPASS CLOUDFLARE
# ============================

def fetch_online_html():
    print(f"[DEBUG] Abrindo página (WebKit stealth): {ONLINE_URL}")

    try:
        with sync_playwright() as pw:

            # WEBKIT — muito menos detectado que Chromium
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
        print(f"[ERRO] Playwright CF bypass: {e}")
        return None

# ============================
# PARSER DA TABELA
# ============================

def parse_online_players(html):
    soup = BeautifulSoup(html, "html.parser")
    online = {}

    tables = soup.find_all("table")
    if not tables:
        print("[WARN] Nenhuma tabela encontrada no HTML.")
        return online

    # acha a tabela certa
    target = None
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
    requests.post(DISCORD_WEBHOOK, json={
        "embeds": [{
            "title": "UP! ⚡",
            "description": f"{player} subiu de {old} → {new}",
            "color": 0x00FF00
        }]
    })

def send_down(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    requests.post(DISCORD_WEBHOOK, json={
        "embeds": [{
            "title": "DOWN! 💀",
            "description": f"{player} caiu de {old} → {new}",
            "color": 0xFF0000
        }]
    })

# ============================
# LOOP
# ============================

def monitor():
    last = load_last_levels()
    print("Monitor iniciado!")

    while True:
        html = fetch_online_html()

        if not html:
            print("❌ HTML vazio, tentando novamente...")
            time.sleep(CHECK_INTERVAL)
            continue

        online = parse_online_players(html)
        print("ONLINE:", list(online.keys()))

        for p in WATCHED_PLAYERS:
            current = online.get(p)
            old = last.get(p)

            if current is None:
                print(f"❌ {p} offline")
                continue

            if old is None:
                print(f"📍 Primeiro registro {p} = {current}")
                last[p] = current
            elif current > old:
                print(f"UP! {p} {old} → {current}")
                send_up(p, old, current)
                last[p] = current
            elif current < old:
                print(f"DOWN! {p} {old} → {current}")
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
