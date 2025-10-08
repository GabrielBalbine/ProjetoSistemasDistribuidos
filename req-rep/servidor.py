import zmq
import json
import datetime
import os
import hashlib
import secrets

# --- FUNÇÕES DE HELPER (PERSISTÊNCIA, SEGURANÇA) ---
def hash_password(password):
    """Gera um hash seguro para a senha."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def carregar_dados(arquivo_json):
    """Carrega dados de um arquivo JSON de forma robusta."""
    if not os.path.exists(arquivo_json): return {}
    try:
        with open(arquivo_json, "r", encoding="utf-8") as f: return json.load(f)
    except json.JSONDecodeError: return {}

def salvar_dados(dados, arquivo_json):
    """Salva um dicionário em um arquivo JSON."""
    with open(arquivo_json, "w", encoding="utf-8") as f: json.dump(dados, f, indent=4, ensure_ascii=False)

def salvar_mensagem(dados_mensagem):
    """Salva o log de uma mensagem recebida."""
    try:
        with open("messages.log", "a", encoding="utf-8") as logfile:
            logfile.write(json.dumps(dados_mensagem, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[ERRO DE PERSISTÊNCIA] Falha ao salvar mensagem: {e}")

# --- CONFIGURAÇÃO E INICIALIZAÇÃO DO COORDENADOR ---
context = zmq.Context()
rep_socket = context.socket(zmq.REP)
rep_socket.connect("tcp://broker:5556")
pub_socket = context.socket(zmq.PUB)
pub_socket.connect("tcp://proxy:5558")

print("Carregando dados...")
usuarios = carregar_dados("usuarios.json")
canais = carregar_dados("canais.json")
active_sessions = {}

user_id_counter = max([int(k) for k in usuarios.keys()], default=-1) + 1
channel_id_counter = max([int(k) for k in canais.keys()], default=-1) + 1
lamport_clock = 0

print(f"✅ Coordenador iniciado.")
print("Conectado aos brokers...")

# --- LOOP PRINCIPAL DO COORDENADOR ---
while True:
    try:
        request = rep_socket.recv_json()
        service = request.get("service")
        data = request.get("data", {})

        # Atualiza o relógio lógico a cada evento de recebimento
        client_lamport_clock = data.get("lamport_clock", 0)
        lamport_clock = max(lamport_clock + 1, client_lamport_clock + 1)
        print(f"[CLOCK] Coordenador recebeu '{service}'. Clock atualizado para: {lamport_clock}")

        if service == "addUser":
            user_nome = data.get("user")
            senha = data.get("senha")
            if not user_nome or not senha:
                rep_socket.send_json({"status": "ERRO", "message": "Usuario e senha sao obrigatorios."})
            elif any(u['user'] == user_nome for u in usuarios.values()):
                rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{user_nome}' ja existe."})
            else:
                hashed_password = hash_password(senha)
                usuarios[str(user_id_counter)] = {"user": user_nome, "password_hash": hashed_password}
                user_id_counter += 1
                salvar_dados(usuarios, "usuarios.json")
                print(f"Novo usuario cadastrado: {user_nome}")
                rep_socket.send_json({"status": "OK", "lamport_clock": lamport_clock})

        elif service == "login":
            user_nome = data.get("user")
            senha = data.get("senha")
            user_data = next((u for u in usuarios.values() if u['user'] == user_nome), None)
            
            if user_data and user_data['password_hash'] == hash_password(senha):
                token = secrets.token_hex(16)
                active_sessions[token] = user_nome
                print(f"Usuario '{user_nome}' logado.")
                rep_socket.send_json({"status": "OK", "token": token, "user": user_nome, "lamport_clock": lamport_clock})
            else:
                print(f"Falha no login para o usuario '{user_nome}'")
                rep_socket.send_json({"status": "ERRO", "message": "Usuario ou senha invalidos.", "lamport_clock": lamport_clock})

        elif service == "getTime":
            server_time_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            rep_socket.send_json({"status": "OK", "server_time_utc": server_time_utc, "lamport_clock": lamport_clock})

        elif service in ["publish", "message", "addChannel"]:
            token = data.get("token")
            user_nome = active_sessions.get(token)
            is_bot = data.get("user", "").startswith("bot-")

            if not user_nome and not is_bot:
                rep_socket.send_json({"status": "ERRO", "message": "Token invalido. Faca login.", "lamport_clock": lamport_clock})
                continue
            
            if is_bot: user_nome = data.get("user")

            if service == "addChannel":
                channel_nome = data.get("titulo", "").lower()
                if any(c['titulo'] == channel_nome for c in canais.values()):
                    rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel_nome}' ja existe.", "lamport_clock": lamport_clock})
                else:
                    canais[str(channel_id_counter)] = {"titulo": channel_nome, "desc": data.get("desc", "")}
                    channel_id_counter += 1
                    salvar_dados(canais, "canais.json")
                    print(f"Usuario '{user_nome}' criou o canal: {channel_nome}")
                    rep_socket.send_json({"status": "OK", "lamport_clock": lamport_clock})
            else:
                lamport_clock += 1 # Incrementa para o evento de envio (publicação)
                print(f"[CLOCK] Coordenador enviando pub. Clock atualizado para: {lamport_clock}")

                conteudo_publicacao = {
                    "user": user_nome,
                    "from": user_nome, # Adicionando 'from' para consistência
                    "message": data.get("message"), 
                    "timestamp": data.get("timestamp"), 
                    "lamport_clock": lamport_clock
                }

                if service == "publish":
                    channel = data.get("channel", "").lower()
                    if any(c['titulo'] == channel for c in canais.values()):
                        pub_socket.send_string(f"{channel} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                        salvar_mensagem(request)
                        rep_socket.send_json({"status": "OK", "lamport_clock": lamport_clock})
                    else:
                        rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel}' nao existe.", "lamport_clock": lamport_clock})

                elif service == "message":
                    dst_user = data.get("dst")
                    if any(u['user'] == dst_user for u in usuarios.values()):
                        pub_socket.send_string(f"{dst_user} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                        salvar_mensagem(request)
                        rep_socket.send_json({"status": "OK", "lamport_clock": lamport_clock})
                    else:
                        rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{dst_user}' nao existe.", "lamport_clock": lamport_clock})
        
        elif service in ["listUsers", "listChannels"]:
            if service == "listUsers":
                rep_socket.send_json(usuarios)
            elif service == "listChannels":
                rep_socket.send_json(canais)
        else:
            rep_socket.send_string(f"ERRO: Servico '{service}' desconhecido.")

    except Exception as e:
        print(f"[ERRO] Ocorreu um erro no servidor: {e}")
        if not rep_socket.closed:
             rep_socket.send_string(f"ERRO: Erro interno no servidor - {e}")