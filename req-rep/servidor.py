import zmq
import json
import datetime
import os
import hashlib
import secrets

# (As funções de helper continuam as mesmas)
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def carregar_dados(arquivo_json):
    if not os.path.exists(arquivo_json): return {}
    try:
        with open(arquivo_json, "r", encoding="utf-8") as f: return json.load(f)
    except json.JSONDecodeError: return {}

def salvar_dados(dados, arquivo_json):
    with open(arquivo_json, "w", encoding="utf-8") as f: json.dump(dados, f, indent=4, ensure_ascii=False)

def salvar_mensagem(dados_mensagem):
    try:
        with open("messages.log", "a", encoding="utf-8") as logfile:
            logfile.write(json.dumps(dados_mensagem, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[ERRO DE PERSISTÊNCIA] Falha ao salvar mensagem: {e}")

# (A inicialização continua a mesma)
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
print(f"✅ Servidor iniciado.")
print("Conectado aos brokers...")

while True:
    try:
        request = rep_socket.recv_json()
        service = request.get("service")
        data = request.get("data", {})
        
        # (Serviços de cadastro e login continuam os mesmos)
        if service == "addUser":
            # ... (código sem alterações)
            user_nome = data.get("user")
            senha = data.get("senha")
            if not user_nome or not senha:
                rep_socket.send_string("ERRO: Usuario e senha sao obrigatorios.")
                continue
            if any(u['user'] == user_nome for u in usuarios.values()):
                rep_socket.send_string(f"ERRO: Usuario '{user_nome}' ja existe.")
            else:
                hashed_password = hash_password(senha)
                usuarios[str(user_id_counter)] = {"user": user_nome, "password_hash": hashed_password}
                user_id_counter += 1
                salvar_dados(usuarios, "usuarios.json")
                print(f"Novo usuario cadastrado: {user_nome}")
                rep_socket.send_string("OK")
        
        elif service == "login":
            user_nome = data.get("user")
            senha = data.get("senha")
            user_data = next((u for u in usuarios.values() if u['user'] == user_nome), None)
            if user_data and user_data['password_hash'] == hash_password(senha):
                token = secrets.token_hex(16)
                active_sessions[token] = user_nome
                print(f"Usuario '{user_nome}' logado com sucesso. Token: {token}")
                rep_socket.send_json({"status": "OK", "token": token, "user": user_nome})
            else:
                print(f"Falha no login para o usuario '{user_nome}'")
                # MUDANÇA UTF-8: Removendo acentos
                rep_socket.send_json({"status": "ERRO", "message": "Usuario ou senha invalidos."})

        elif service in ["publish", "message", "addChannel"]:
            token = data.get("token")
            user_nome = active_sessions.get(token)
            
            # MUDANÇA PARA O BOT: Verifica se a requisição é de um bot
            is_bot = data.get("user", "").startswith("bot-")

            # MUDANÇA PARA O BOT: Se o token for inválido E não for um bot, bloqueia
            if not user_nome and not is_bot:
                # MUDANÇA UTF-8: Removendo acentos
                rep_socket.send_json({"status": "ERRO", "message": "Token invalido ou sessao expirada. Faca login."})
                continue
            
            # MUDANÇA PARA O BOT: Se for um bot, confia no nome que ele enviou
            if is_bot:
                user_nome = data.get("user")

            # --- Roteamento de serviços protegidos ---
            if service == "addChannel":
                # ... (código sem alterações)
                channel_nome = data.get("titulo", "").lower()
                if any(c['titulo'] == channel_nome for c in canais.values()):
                    rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel_nome}' ja existe."})
                else:
                    data['titulo'] = channel_nome
                    canais[str(channel_id_counter)] = {"titulo": data['titulo'], "desc": data['desc']}
                    channel_id_counter += 1
                    salvar_dados(canais, "canais.json")
                    print(f"Usuario '{user_nome}' criou o canal: {data['titulo']}")
                    rep_socket.send_json({"status": "OK"})
            
            elif service == "publish":
                # ... (código sem alterações)
                channel = data.get("channel", "").lower()
                if any(c['titulo'] == channel for c in canais.values()):
                    conteudo_publicacao = {"user": user_nome, "message": data.get("message"), "timestamp": data.get("timestamp")}
                    pub_socket.send_string(f"{channel} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                    salvar_mensagem(request)
                    rep_socket.send_json({"status": "OK"})
                else:
                    rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel}' nao existe."})

            elif service == "message":
                # ... (código sem alterações)
                dst_user = data.get("dst")
                if any(u['user'] == dst_user for u in usuarios.values()):
                    conteudo_publicacao = {"from": user_nome, "message": data.get("message"), "timestamp": data.get("timestamp")}
                    pub_socket.send_string(f"{dst_user} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                    salvar_mensagem(request)
                    rep_socket.send_json({"status": "OK"})
                else:
                    rep_socket.send_json({"status": "ERRO", "message": f"Usuario '{dst_user}' nao existe."})
        
        elif service in ["listUsers", "listChannels"]:
            # ... (código sem alterações)
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