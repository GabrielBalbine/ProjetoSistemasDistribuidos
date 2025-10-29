import zmq
import json
import datetime
import os
import hashlib
import secrets
import time
import threading
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

# --- FUNÇÕES DE HELPER ---
def hash_password(password): return hashlib.sha256(password.encode('utf-8')).hexdigest()
def carregar_dados(arquivo_json):
    path = os.path.join(ELECTION_DIR, arquivo_json)
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}
def salvar_dados(dados, arquivo_json):
    path = os.path.join(ELECTION_DIR, arquivo_json)
    with open(path, "w", encoding="utf-8") as f: json.dump(dados, f, indent=4, ensure_ascii=False)
def salvar_mensagem(dados_mensagem):
    path = os.path.join(ELECTION_DIR, "messages.log")
    try:
        with open(path, "a", encoding="utf-8") as logfile:
            logfile.write(json.dumps(dados_mensagem, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[{MY_ID}] Erro ao salvar log de mensagem: {e}")

# --- LÓGICA DE ELEIÇÃO POR LOCK FILE ---
def try_to_become_leader():
    try:
        with open(LEADER_FILE, "x") as f: f.write(f"{MY_ID},{time.time()}")
        return True
    except FileExistsError: return False
    except Exception: return False

# --- LOOP PRINCIPAL UNIFICADO ---
def main_loop():
    global STATE
    context = zmq.Context()
    
    usuarios, canais = {}, {}
    user_id_counter, channel_id_counter = 0, 0
    
    rep_socket, pub_socket = None, None

    while True:
        if STATE == "LEADER":
            if rep_socket is None:
                print(f"[{MY_ID}] Assumi a liderança! Conectando e carregando estado...")
                usuarios = carregar_dados("usuarios.json")
                canais = carregar_dados("canais.json")
                user_id_counter = max([int(k) for k in usuarios.keys()], default=-1) + 1
                channel_id_counter = max([int(k) for k in canais.keys()], default=-1) + 1
                
                rep_socket = context.socket(zmq.REP)
                rep_socket.connect("tcp://broker:5556")
                pub_socket = context.socket(zmq.PUB)
                pub_socket.connect("tcp://proxy:5558")
            
            try:
                with open(LEADER_FILE, "w") as f: f.write(f"{MY_ID},{time.time()}")
            except Exception as e:
                print(f"[{MY_ID}-LÍDER] Erro ao escrever heartbeat, renunciando: {e}")
                STATE = "FOLLOWER"
                continue

            try:
                request = rep_socket.recv_json(flags=zmq.NOBLOCK)
                service = request.get("service")
                data = request.get("data", {})
                print(f"[{MY_ID}-LÍDER] Processando serviço: {service}")

                # --- LÓGICA COM JWT ---
                if service == "addUser":
                    user_nome = data.get("user")
                    senha = data.get("senha")
                    if any(u['user'] == user_nome for u in usuarios.values()):
                        rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{user_nome}' ja existe."})
                    else:
                        usuarios[str(user_id_counter)] = {"user": user_nome, "password_hash": hash_password(senha)}
                        user_id_counter += 1
                        salvar_dados(usuarios, "usuarios.json")
                        rep_socket.send_json({"status": "OK"})
                elif service == "login":
                    user_nome = data.get("user")
                    senha = data.get("senha")
                    user_data = next((u for u in usuarios.values() if u['user'] == user_nome), None)
                    if user_data and user_data['password_hash'] == hash_password(senha):
                        payload = {"user": user_nome, "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)}
                        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
                        rep_socket.send_json({"status": "OK", "token": token, "user": user_nome})
                    else:
                        rep_socket.send_json({"status": "ERRO", "message": "Usuario ou senha invalidos."})
                elif service == "listChannels":
                    rep_socket.send_json(canais)
                elif service == "listUsers":
                    rep_socket.send_json(usuarios)
                else: # SERVIÇOS PROTEGIDOS
                    try:
                        token = data.get("token")
                        is_bot = data.get("user", "").startswith("bot-")

                        if is_bot:
                            user_nome = data.get("user")
                        else:
                            decoded_payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                            user_nome = decoded_payload['user']
                        
                        if service == "addChannel":
                            channel_nome = data.get("titulo", "").lower()
                            if any(c['titulo'] == channel_nome for c in canais.values()):
                                rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel_nome}' ja existe."})
                            else:
                                canais[str(channel_id_counter)] = {"titulo": channel_nome, "desc": data.get("desc", "")}
                                channel_id_counter += 1
                                salvar_dados(canais, "canais.json")
                                rep_socket.send_json({"status": "OK"})
                        elif service == "publish":
                            channel = data.get("channel", "").lower()
                            if any(c['titulo'] == channel for c in canais.values()):
                                conteudo_publicacao = {"user": user_nome, "message": data.get("message"), "timestamp": data.get("timestamp")}
                                pub_socket.send_string(f"{channel} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                                salvar_mensagem(request)
                                rep_socket.send_json({"status": "OK"})
                            else:
                                rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel}' nao existe."})
                        elif service == "message":
                            dst_user = data.get("dst")
                            if any(u['user'] == dst_user for u in usuarios.values()):
                                conteudo_publicacao = {"from": user_nome, "message": data.get("message"), "timestamp": data.get("timestamp")}
                                pub_socket.send_string(f"{dst_user} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                                salvar_mensagem(request)
                                rep_socket.send_json({"status": "OK"})
                            else:
                                rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{dst_user}' nao existe."})
                        else:
                            rep_socket.send_json({"status": "ERRO", "message": f"Servico '{service}' nao reconhecido.", "processed_by": MY_ID})

                    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                        rep_socket.send_json({"status": "ERRO", "message": "Token invalido ou expirado. Faca login novamente."})
            except zmq.Again:
                time.sleep(0.1)
        
        else: # STATE == "FOLLOWER"
            if rep_socket is not None:
                print(f"[{MY_ID}] Não sou mais o líder. Desconectando dos brokers.")
                rep_socket.close(); pub_socket.close()
                rep_socket, pub_socket = None, None
            try:
                with open(LEADER_FILE, "r") as f:
                    content = f.read()
                    if ',' in content:
                        leader_id_str, last_hb_str = content.split(',')
                        last_hb = float(last_hb_str)
                        if time.time() - last_hb > HEARTBEAT_TIMEOUT:
                            print(f"[{MY_ID}] Timeout! Líder {leader_id_str} parece morto. Removendo lock file...")
                            try: os.remove(LEADER_FILE)
                            except OSError: pass
                    else: time.sleep(0.1)
            except FileNotFoundError:
                if try_to_become_leader():
                    STATE = "LEADER"
            except Exception as e:
                print(f"[{MY_ID}] Erro como seguidor: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    print(f"--- Servidor PID {os.getpid()} iniciando com ID: {MY_ID} ---")
    os.makedirs(ELECTION_DIR, exist_ok=True)
    if MY_ID == 1 and os.path.exists(LEADER_FILE):
        try: os.remove(LEADER_FILE)
        except OSError: pass
    main_loop()