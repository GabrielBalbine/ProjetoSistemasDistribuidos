import zmq
import json
import datetime
import os

# --- FUNÇÕES DE PERSISTÊNCIA DE DADOS ---
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

print("Carregando dados de usuários e canais...")
usuarios = carregar_dados("usuarios.json")
canais = carregar_dados("canais.json")

user_id_counter = max([int(k) for k in usuarios.keys()], default=-1) + 1
channel_id_counter = max([int(k) for k in canais.keys()], default=-1) + 1

print(f"✅ Servidor iniciado. {len(usuarios)} usuários e {len(canais)} canais carregados.")
print("Conectado aos brokers...")

# --- LOOP PRINCIPAL DO SERVIDOR ---
while True:
    try:
        request = rep_socket.recv_json()
        service = request.get("service")
        data = request.get("data", {})
        
        if service == "addUser":
            user_nome = data.get("user")
            if any(u['user'] == user_nome for u in usuarios.values()):
                rep_socket.send_string(f"ERRO: Usuário '{user_nome}' já existe.")
            else:
                usuarios[str(user_id_counter)] = data
                user_id_counter += 1
                salvar_dados(usuarios, "usuarios.json")
                print(f"Novo usuário adicionado: {data}. Total: {len(usuarios)}")
                rep_socket.send_string("OK")
        
        elif service == "addChannel":
            channel_nome = data.get("titulo", "").lower()
            if any(c['titulo'] == channel_nome for c in canais.values()):
                rep_socket.send_string(f"ERRO: Canal '{channel_nome}' já existe.")
            else:
                data['titulo'] = channel_nome
                canais[str(channel_id_counter)] = data
                channel_id_counter += 1
                salvar_dados(canais, "canais.json")
                print(f"Novo canal adicionado: {data}. Total: {len(canais)}")
                rep_socket.send_string("OK")

        elif service == "listUsers":
            rep_socket.send_json(usuarios)

        elif service == "listChannels":
            rep_socket.send_json(canais)

        elif service == "publish":
            user = data.get("user")
            channel = data.get("channel", "").lower()
            if any(c['titulo'] == channel for c in canais.values()):
                conteudo_publicacao = {"user": user, "message": data.get("message"), "timestamp": data.get("timestamp")}
                pub_socket.send_string(f"{channel} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                salvar_mensagem(request)
                reply = {"service": "publish", "data": {"status": "OK", "timestamp": datetime.datetime.now().isoformat()}}
                rep_socket.send_json(reply)
            else:
                reply = {"service": "publish", "data": {"status": "erro", "message": f"Canal '{channel}' não existe.", "timestamp": datetime.datetime.now().isoformat()}}
                rep_socket.send_json(reply)

        elif service == "message":
            dst_user = data.get("dst")
            if any(u['user'] == dst_user for u in usuarios.values()):
                conteudo_publicacao = {"from": data.get("src"), "message": data.get("message"), "timestamp": data.get("timestamp")}
                pub_socket.send_string(f"{dst_user} {json.dumps(conteudo_publicacao, ensure_ascii=False)}")
                salvar_mensagem(request)
                reply = {"service": "message", "data": {"status": "OK", "timestamp": datetime.datetime.now().isoformat()}}
                rep_socket.send_json(reply)
            else:
                reply = {"service": "message", "data": {"status": "erro", "message": f"Usuário '{dst_user}' não existe.", "timestamp": datetime.datetime.now().isoformat()}}
                rep_socket.send_json(reply)
        else:
            rep_socket.send_string("ERRO: Serviço desconhecido.")

    except Exception as e:
        print(f"[ERRO] Ocorreu um erro no servidor: {e}")
        if not rep_socket.closed:
             rep_socket.send_string(f"ERRO: Erro interno no servidor - {e}")