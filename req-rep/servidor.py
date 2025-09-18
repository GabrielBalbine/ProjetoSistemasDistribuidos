import zmq
import json
import datetime
import os
import hashlib
import secrets

# --- FUNÇÕES DE SEGURANÇA E PERSISTÊNCIA ---
def hash_password(password):
    """Gera um hash seguro para a senha."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def carregar_dados(arquivo_json):
    """Carrega dados de um arquivo JSON. Se não existir, estiver vazio ou corrompido, retorna um dict vazio."""
    if not os.path.exists(arquivo_json):
        return {}
    try:
        with open(arquivo_json, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def salvar_dados(dados, arquivo_json):
    """Salva um dicionário em um arquivo JSON de forma legível."""
    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def salvar_mensagem(dados_mensagem):
    """Salva o log de uma mensagem recebida."""
    try:
        with open("messages.log", "a", encoding="utf-8") as logfile:
            logfile.write(json.dumps(dados_mensagem, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[ERRO DE PERSISTÊNCIA] Falha ao salvar mensagem: {e}")

# --- CONFIGURAÇÃO E INICIALIZAÇÃO ---
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

# --- LOOP PRINCIPAL DO SERVIDOR ---
while True:
    try:
        request = rep_socket.recv_json()
        service = request.get("service")
        data = request.get("data", {})
        
        if service == "addUser":
            user_nome = data.get("user")
            senha = data.get("senha")
            if not user_nome or not senha:
                rep_socket.send_string("ERRO: Usuário e senha são obrigatórios.")
                continue

            if any(u['user'] == user_nome for u in usuarios.values()):
                rep_socket.send_string(f"ERRO: Usuário '{user_nome}' já existe.")
            else:
                hashed_password = hash_password(senha)
                usuarios[str(user_id_counter)] = {"user": user_nome, "password_hash": hashed_password}
                user_id_counter += 1
                salvar_dados(usuarios, "usuarios.json")
                print(f"Novo usuário cadastrado: {user_nome}")
                rep_socket.send_string("OK")

        elif service == "login":
            user_nome = data.get("user")
            senha = data.get("senha")
            user_data = next((u for u in usuarios.values() if u['user'] == user_nome), None)
            
            if user_data and user_data['password_hash'] == hash_password(senha):
                token = secrets.token_hex(16)
                active_sessions[token] = user_nome
                print(f"Usuário '{user_nome}' logado com sucesso. Token: {token}")
                rep_socket.send_json({"status": "OK", "token": token, "user": user_nome})
            else:
                print(f"Falha no login para o usuário '{user_nome}'")
                rep_socket.send_json({"status": "ERRO", "message": "Usuário ou senha inválidos."})

        elif service in ["publish", "message", "addChannel"]:
            token = data.get("token")
            user_nome = active_sessions.get(token)
            
            if not user_nome:
                rep_socket.send_json({"status": "ERRO", "message": "Token inválido ou sessão expirada. Faça login."})
                continue
            
            # --- Roteamento de serviços protegidos ---
            if service == "addChannel":
                channel_nome = data.get("titulo", "").lower()
                if any(c['titulo'] == channel_nome for c in canais.values()):
                    rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel_nome}' já existe."})
                else:
                    data['titulo'] = channel_nome
                    canais[str(channel_id_counter)] = {"titulo": data['titulo'], "desc": data['desc']}
                    channel_id_counter += 1
                    salvar_dados(canais, "canais.json")
                    print(f"Usuário '{user_nome}' criou o canal: {data['titulo']}")
                    rep_socket.send_json({"status": "OK"})

            elif service == "publish":
                channel = data.get("channel", "").lower()
                if any(c['titulo'] == channel for c in canais.values()):
                    conteudo_publicacao = {"user": user_nome, "message": data.get("message"), "timestamp": data.get("timestamp")}
                    pub_socket.send_string(f"{channel} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                    salvar_mensagem(request)
                    rep_socket.send_json({"status": "OK"})
                else:
                    rep_socket.send_json({"status": "ERRO", "message": f"Canal '{channel}' não existe."})

            elif service == "message":
                dst_user = data.get("dst")
                if any(u['user'] == dst_user for u in usuarios.values()):
                    conteudo_publicacao = {"from": user_nome, "message": data.get("message"), "timestamp": data.get("timestamp")}
                    pub_socket.send_string(f"{dst_user} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                    salvar_mensagem(request)
                    rep_socket.send_json({"status": "OK"})
                else:
                    rep_socket.send_json({"status": "ERRO", "message": f"Usuário '{dst_user}' não existe."})
        
        elif service in ["listUsers", "listChannels"]:
            # Serviços de listagem continuam públicos (não precisam de token)
            if service == "listUsers":
                rep_socket.send_json(usuarios)
            elif service == "listChannels":
                rep_socket.send_json(canais)
        else:
            rep_socket.send_string(f"ERRO: Serviço '{service}' desconhecido.")

    except Exception as e:
        print(f"[ERRO] Ocorreu um erro no servidor: {e}")
        if not rep_socket.closed:
             rep_socket.send_string(f"ERRO: Erro interno no servidor - {e}")