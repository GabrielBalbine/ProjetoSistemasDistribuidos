# servidor_corrigido.py
import zmq
import json
import datetime
import os
import hashlib
import time
import jwt

# --- CONSTANTES ---
ELECTION_DIR = "/app/election"
LEADER_FILE = os.path.join(ELECTION_DIR, "leader.lock")
HEARTBEAT_INTERVAL = 2.0
HEARTBEAT_TIMEOUT = 5.0
SECRET_KEY = "VAI_TRICOLOR_EM_2025"

# --- ESTADO GLOBAL DO SERVIDOR ---
MY_ID = int(os.environ.get("SERVER_ID", 0))
STATE = "FOLLOWER"

# --- Relógio de Lamport ---
LAMPORT_CLOCK = 0

def lamport_tick():
    global LAMPORT_CLOCK
    LAMPORT_CLOCK += 1
    return LAMPORT_CLOCK

def lamport_update(received):
    global LAMPORT_CLOCK
    try:
        r = int(received)
    except Exception:
        r = 0
    LAMPORT_CLOCK = max(LAMPORT_CLOCK, r) + 1
    return LAMPORT_CLOCK

# --- Helpers para persistência ---
def hash_password(password): return hashlib.sha256(password.encode('utf-8')).hexdigest()

def carregar_dados(arquivo_json):
    path = os.path.join(ELECTION_DIR, arquivo_json)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def salvar_dados(dados, arquivo_json):
    path = os.path.join(ELECTION_DIR, arquivo_json)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def salvar_mensagem(dados_mensagem):
    path = os.path.join(ELECTION_DIR, "messages.log")
    try:
        with open(path, "a", encoding="utf-8") as logfile:
            logfile.write(json.dumps(dados_mensagem, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[{MY_ID}] Erro ao salvar log de mensagem: {e}")

# --- Eleição por lock file ---
def try_to_become_leader():
    try:
        with open(LEADER_FILE, "x") as f:
            f.write(f"{MY_ID},{time.time()}")
        return True
    except FileExistsError:
        return False
    except Exception:
        return False

# --- Helpers para inscrição de bots ---
def is_bot_name(name):
    if not name: return False
    return str(name).startswith("bot-") or str(name).startswith("bot-go-")

def ensure_bot_subscribed(bot_name, canais, subscriptions):
    modified = False
    if not is_bot_name(bot_name):
        return False
    # normaliza canais: pegar títulos (lower().strip())
    channel_titles = [c.get("titulo", "").lower().strip() for c in canais.values() if c.get("titulo")]
    if bot_name not in subscriptions:
        subscriptions[bot_name] = []
        modified = True
    for title in channel_titles:
        if title not in subscriptions.get(bot_name, []):
            subscriptions[bot_name].append(title)
            modified = True
    return modified

def ensure_all_bots_subscribed(canais, subscriptions):
    modified = False
    # também podemos inscrever bots conhecidos na listagem atual
    for user in list(subscriptions.keys()):
        if is_bot_name(user):
            if ensure_bot_subscribed(user, canais, subscriptions):
                modified = True
    return modified

# --- Loop principal (RESP/ PUB via broker/proxy) ---
def main_loop():
    global STATE, LAMPORT_CLOCK

    context = zmq.Context()

    usuarios, canais = {}, {}
    subscriptions = {}  # formato: { "username": ["canal1", "canal2"] }
    user_id_counter, channel_id_counter = 0, 0

    rep_socket, pub_socket = None, None

    while True:
        if STATE == "LEADER":
            if rep_socket is None:
                print(f"[{MY_ID}] Assumi a liderança! Conectando e carregando estado...")
                usuarios = carregar_dados("usuarios.json")
                canais = carregar_dados("canais.json")
                subscriptions = carregar_dados("subscriptions.json")
                # normaliza keys que possam ter sido salvas com espaços
                # (mantemos formato id -> {titulo,desc})
                user_id_counter = max([int(k) for k in usuarios.keys()], default=-1) + 1
                channel_id_counter = max([int(k) for k in canais.keys()], default=-1) + 1

                # Conectar REP ao broker (DEALER)
                rep_socket = context.socket(zmq.REP)
                rep_socket.connect("tcp://broker:5556")

                # Conectar PUB ao proxy (XSUB)
                pub_socket = context.socket(zmq.PUB)
                pub_socket.connect("tcp://proxy:5558")

                # garantir que bots já em subscriptions estejam inscritos em todos os canais
                if ensure_all_bots_subscribed(canais, subscriptions):
                    try:
                        salvar_dados(subscriptions, "subscriptions.json")
                    except Exception:
                        pass

            # atualiza heartbeat no lock file
            try:
                with open(LEADER_FILE, "w") as f:
                    f.write(f"{MY_ID},{time.time()}")
            except Exception as e:
                print(f"[{MY_ID}-LÍDER] Erro ao escrever heartbeat, renunciando: {e}")
                STATE = "FOLLOWER"
                continue

            try:
                request = rep_socket.recv_json(flags=zmq.NOBLOCK)
                # request tem formato: { "service": "...", "data": {...} }
                data = request.get("data", {})

                # Atualiza relógio com o valor recebido do cliente
                received_lamport = data.get("lamport_clock", 0)
                lamport_update(received_lamport)
                lamport_tick()  # tick pelo evento de receber e iniciar processamento

                service = request.get("service")
                print(f"[{MY_ID}-LÍDER|lamport={LAMPORT_CLOCK}] Processando serviço: {service}")

                # Serviços públicos
                if service == "addUser":
                    lamport_tick()
                    user_nome = data.get("user")
                    senha = data.get("senha")
                    if any(u['user'] == user_nome for u in usuarios.values()):
                        rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{user_nome}' ja existe.", "lamport_clock": lamport_tick()})
                    else:
                        usuarios[str(user_id_counter)] = {"user": user_nome, "password_hash": hash_password(senha)}
                        user_id_counter += 1
                        salvar_dados(usuarios, "usuarios.json")
                        rep_socket.send_json({"status": "OK", "lamport_clock": lamport_tick()})

                elif service == "login":
                    lamport_tick()
                    user_nome = data.get("user")
                    senha = data.get("senha")
                    user_data = next((u for u in usuarios.values() if u['user'] == user_nome), None)
                    if user_data and user_data['password_hash'] == hash_password(senha):
                        payload = {"user": user_nome, "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)}
                        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
                        rep_socket.send_json({"status": "OK", "token": token, "user": user_nome, "lamport_clock": lamport_tick()})
                    else:
                        rep_socket.send_json({"status": "ERRO", "message": "Usuario ou senha invalidos.", "lamport_clock": lamport_tick()})

                elif service == "listChannels":
                    # Cliente espera receber o dict bruto de canais (id -> {titulo,desc})
                    rep_socket.send_json(canais)

                elif service == "listUsers":
                    # idem: retorna o dict bruto de users
                    rep_socket.send_json(usuarios)

                elif service == "getTime":
                    # usado pelo cliente para sync_time; retornamos um objeto
                    lamport_tick()
                    rep_socket.send_json({
                        "server_time_utc": datetime.datetime.utcnow().isoformat() + "Z",
                        "lamport_clock": lamport_tick()
                    })

                else:
                    # Serviços protegidos — validamos token (exceto bots)
                    try:
                        token = data.get("token")
                        is_bot = data.get("user", "").startswith("bot-") or data.get("user", "").startswith("bot-go-")

                        if is_bot:
                            user_nome = data.get("user")
                        else:
                            decoded_payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                            user_nome = decoded_payload['user']

                        # Se é bot, garantir inscrição em todos os canais atuais
                        if is_bot:
                            if ensure_bot_subscribed(user_nome, canais, subscriptions):
                                try:
                                    salvar_dados(subscriptions, "subscriptions.json")
                                except Exception:
                                    pass

                        lamport_tick()

                        # --- addChannel  ---
                        if service == "addChannel":
                            channel_nome = data.get("titulo", "").lower().strip()
                            if any(c['titulo'] == channel_nome for c in canais.values()):
                                rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel_nome}' ja existe.", "lamport_clock": lamport_tick()})
                            else:
                                canais[str(channel_id_counter)] = {"titulo": channel_nome, "desc": data.get("desc", "")}
                                channel_id_counter += 1
                                salvar_dados(canais, "canais.json")
                                # Ao criar novo canal, garantir que bots fiquem inscritos nele
                                if ensure_all_bots_subscribed(canais, subscriptions):
                                    try:
                                        salvar_dados(subscriptions, "subscriptions.json")
                                    except Exception:
                                        pass
                                rep_socket.send_json({"status": "OK", "lamport_clock": lamport_tick()})

                        # ---  subscribe ---
                        elif service == "subscribe":
                            channel_req = data.get("channel", "").lower().strip()
                            if not any(c['titulo'] == channel_req for c in canais.values()):
                                rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel_req}' nao existe.", "lamport_clock": lamport_tick()})
                            else:
                                # garantir estrutura
                                if user_nome not in subscriptions:
                                    subscriptions[user_nome] = []
                                if channel_req not in subscriptions[user_nome]:
                                    subscriptions[user_nome].append(channel_req)
                                    salvar_dados(subscriptions, "subscriptions.json")
                                rep_socket.send_json({"status": "OK", "message": f"{user_nome} inscrito em '{channel_req}'", "lamport_clock": lamport_tick()})

                        # --- publish ---
                        elif service == "publish":
                            channel = data.get("channel", "").lower().strip()
                            if not any(c['titulo'] == channel for c in canais.values()):
                                rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel}' nao existe.", "lamport_clock": lamport_tick()})
                            else:
                                # valida inscrição (bots já foram inscritos automaticamente acima)
                                user_subs = subscriptions.get(user_nome, [])
                                if channel not in user_subs:
                                    rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{user_nome}' nao inscrito em '{channel}'.", "lamport_clock": lamport_tick()})
                                else:
                                    # inclua lamport_clock no conteúdo publicado para os subscribers
                                    conteudo_publicacao = {
                                        "user": user_nome,
                                        "message": data.get("message"),
                                        "timestamp": data.get("timestamp"),
                                        "lamport_clock": LAMPORT_CLOCK
                                    }
                                    # Pub no proxy: topico = nome do canal
                                    pub_socket.send_string(f"{channel} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                                    salvar_mensagem({**request, "lamport_clock": LAMPORT_CLOCK})
                                    rep_socket.send_json({"status": "OK", "lamport_clock": lamport_tick()})

                        elif service == "message":
                            dst_user = data.get("dst")
                            if any(u['user'] == dst_user for u in usuarios.values()):
                                conteudo_publicacao = {
                                    "from": user_nome,
                                    "message": data.get("message"),
                                    "timestamp": data.get("timestamp"),
                                    "lamport_clock": LAMPORT_CLOCK
                                }
                                pub_socket.send_string(f"{dst_user} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                                salvar_mensagem({**request, "lamport_clock": LAMPORT_CLOCK})
                                rep_socket.send_json({"status": "OK", "lamport_clock": lamport_tick()})
                            else:
                                rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{dst_user}' nao existe.", "lamport_clock": lamport_tick()})

                        else:
                            rep_socket.send_json({"status": "ERRO", "message": f"Servico '{service}' nao reconhecido.", "lamport_clock": lamport_tick()})

                    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                        rep_socket.send_json({"status": "ERRO", "message": "Token invalido ou expirado. Faca login novamente.", "lamport_clock": lamport_tick()})

            except zmq.Again:
                # sem requests no momento
                time.sleep(0.1)
            except Exception as e:
                print(f"[{MY_ID}-LÍDER] Erro ao processar request: {e}")
                time.sleep(0.1)

        else:  # FOLLOWER
            if rep_socket is not None:
                print(f"[{MY_ID}] Não sou mais o líder. Desconectando dos brokers.")
                rep_socket.close(); pub_socket.close()
                rep_socket, pub_socket = None, None
            try:
                with open(LEADER_FILE, "r") as f:
                    content = f.read()
                    if ',' in content:
                        leader_id_str, last_hb_str = content.split(',', 1)
                        last_hb = float(last_hb_str)
                        if time.time() - last_hb > HEARTBEAT_TIMEOUT:
                            print(f"[{MY_ID}] Timeout! Líder {leader_id_str} parece morto. Removendo lock file...")
                            try: os.remove(LEADER_FILE)
                            except OSError: pass
                    else:
                        time.sleep(0.1)
            except FileNotFoundError:
                # tentar virar líder
                if try_to_become_leader():
                    STATE = "LEADER"
            except Exception as e:
                print(f"[{MY_ID}] Erro como seguidor: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    print(f"--- Servidor PID {os.getpid()} iniciando com ID: {MY_ID} ---")
    os.makedirs(ELECTION_DIR, exist_ok=True)
    # reinicia lock file no servidor 1
    if MY_ID == 1 and os.path.exists(LEADER_FILE):
        try: os.remove(LEADER_FILE)
        except OSError: pass
    main_loop()
