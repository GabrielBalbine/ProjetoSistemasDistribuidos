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