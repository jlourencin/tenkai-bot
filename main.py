import os
import time
import json
import threading
import re
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string

# =========================
# CONFIGURAÇÕES PRINCIPAIS
# =========================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")

_raw_players = os.environ.get("WATCHED_PLAYERS", "")
WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

CHECK_INTERVAL = 60
MIN_LEVEL = 1
STATE_FILE = "last_levels.json"

# Turnstile (Cloudflare) – OPCIONAL
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY")
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)

# =========================
# FLASK APP
# =========================

app = Flask(__name__)

HTML_INDEX = """
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8">
    <title>Bot de Level + Turnstile</title>

    {% if turnstile_enabled %}
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
    {% endif %}
  </head>

  <body>
    <h1>✅ Bot de Level está rodando</h1>
    <p><strong>Jogadores monitorados:</strong> {{ players }}</p>
    <p><strong>Intervalo de checagem:</strong> {{ interval }}s</p>

    <hr>

    <h2>Teste Turnstile</h2>

    {% if not turnstile_enabled %}
      <p style="color: orange;">
        ⚠️ Turnstile DESATIVADO — rodando em modo simulado.<br>
        Configure TURNSTILE_SITE_KEY e TURNSTILE_SECRET_KEY no Railway depois.
      </p>
    {% endif %}

    <form method="post" action="/turnstile-check">
      <label>Digite algo:</label><br>
      <input type="text" name="username" required><br><br>

      {% if turnstile_enabled %}
        <div class="cf-challenge" data-sitekey="{{ site_key }}"></div>
      {% else %}
        <p>(Widget simulado — sem validação real)</p>
      {% endif %}

      <br>
      <button type="submit">Enviar</button>
    </form>
  </body>
</html>
"""

HTML_RESULT = """
<!doctype html>
<html lang="pt-BR">
  <head><meta charset="utf-8"><title>Resultado Turnstile</title></head>
  <body>
    <h1>{{ message }}</h1>
    <a href="/">Voltar</a>
  </body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    players_txt = ", ".join(WATCHED_PLAYERS) if WATCHED_PLAYERS else "nenhum"
    return render_template_string(
        HTML_INDEX,
        players=players_txt,
        interval=CHECK_INTERVAL,
        turnstile_enabled=TURNSTILE_ENABLED,
        site_key=TURNSTILE_SITE_KEY,
    )


@app.route("/turnstile-check", methods=["POST"])
def turnstile_check():
    username = (request.form.get("username") or "").strip()
    token = request.form.get("cf-turnstile-response", "")
    ip = request.remote_addr

    print(f"[INFO] Turnstile check: user='{username}' IP={ip}")

    if not TURNSTILE_ENABLED:
        print("[SIMULADO] Turnstile aceito automaticamente.")
        msg = f"🟢 (SIMULADO) Turnstile OK para: {username}"
        return render_template_string(HTML_RESULT, message=msg), 200

    ok = verify_turnstile(token, ip)

    if not ok:
        msg = "❌ Falha na verificação Cloudflare Turnstile."
        print(f"[BLOQUEADO] user='{username}' IP={ip}")
        return render_template_string(HTML_RESULT, message=msg), 403

    msg = f"✅ Turnstile REAL OK para: {username}"
    print(f"[ACEITO] user='{username}' IP={ip} - CAPTCHA OK")
    return render_template_string(HTML_RESULT, message=msg), 200


@app.route("/health")
def health():
    return "OK", 200


# =========================
# VALIDADOR TURNSTILE
# =========================

def verify_turnstile(token, remote_ip=None):
    if not TURNSTILE_ENABLED:
        return True  # modo simulado

    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    data = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        r = requests.post(url, data=data, timeout=10)
        r.raise_for_status()
        result = r.json()
        print("[DEBUG] Turnstile:", result)
        return result.get("success", False)
    except Exception as e:
        print("[ERRO] Falha Turnstile:", e)
        return False


# =========================
# BOT DE LEVEL
# =========================

def load_last_levels():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_last_levels(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_profile_url(name: str) -> str:
    """
    Monta a URL do perfil:
    Exemplo: https://ntotenkai.com.br/characters/Alienwarre
    """
    encoded = quote_plus(name)
    return f"https://ntotenkai.com.br/characters/{encoded}"


def get_level_from_profile(name: str):
    """
    Acessa a página de perfil do char e extrai o level.
    Retorna int ou None.
    """
    url = build_profile_url(name)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        )
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] Perfil URL {name}: {url} | status {r.status_code}")
    except Exception as e:
        print(f"[ERRO] Falha ao acessar {name}: {e}")
        return None

    if r.status_code != 200:
        print(f"[ERRO] Perfil de {name} retornou {r.status_code}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Procura qualquer <td> cujo texto contenha "level" (com ou sem dois pontos)
    def is_level_label(text):
        if not text:
            return False
        t = text.strip().lower()
        t = t.replace(":", "")
        return t == "level"

    label_td = soup.find("td", string=is_level_label)
    if not label_td:
        print(f"[ERRO] Não encontrei a linha de Level para {name}")
        return None

    value_td = label_td.find_next("td")
    if not value_td:
        print(f"[ERRO] Não encontrei a célula de valor de Level para {name}")
        return None

    raw = value_td.get_text(strip=True)
    # Pega o primeiro número que aparecer (ex: "527", "527 (Elite)", etc.)
    m = re.search(r"\d+", raw)
    if not m:
        print(f"[ERRO] Valor de level não numérico para {name}: {raw!r}")
        return None

    level = int(m.group(0))
    return level


def send_up_embed(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    diff = new - old
    embed = {
        "title": "☠️ UPOU PARA MORRER",
        "description": f"**{player}** subiu de nível e já vai morrer kkkk xd ☠️🔪",
        "color": 0x00FF00,
        "fields": [
            {"name": "Jogador", "value": player, "inline": True},
            {"name": "Level", "value": f"{old} → {new} (+{diff})", "inline": True},
        ],
    }
    try:
        requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print("[ERRO] Falha ao enviar embed de UP:", e)


def send_death_embed(player, old, new):
    if not DISCORD_WEBHOOK:
        return
    embed = {
        "title": "💀 XIII MORREU NOOB",
        "description": f"**{player}** morreu noobasso 💀",
        "color": 0xFF0000,
        "fields": [
            {"name": "Jogador", "value": player, "inline": True},
            {"name": "Level", "value": f"{old} → {new}", "inline": True},
        ],
    }
    try:
        requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print("[ERRO] Falha ao enviar embed de MORTE:", e)


def monitor_loop():
    last_levels = load_last_levels()
    print("▶ Monitorando:", WATCHED_PLAYERS)

    while True:
        for player in WATCHED_PLAYERS:
            level = get_level_from_profile(player)
            if level is None:
                print(f"❌ {player}: perfil inválido")
                continue

            old = last_levels.get(player)

            if old is None:
                print(f"🟦 Primeiro registro: {player} = {level}")
                last_levels[player] = level

            elif level > old:
                print(f"🚀 UP: {player} {old} → {level}")
                send_up_embed(player, old, level)
                last_levels[player] = level

            elif level < old:
                print(f"💀 DOWN: {player} {old} → {level}")
                send_death_embed(player, old, level)
                last_levels[player] = level

            else:
                print(f"✔ {player}: {level}")

        save_last_levels(last_levels)
        print(f"⏳ Aguardando {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
