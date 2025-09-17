import zmq
import datetime
import threading
import json
import sys
import time

def message_listener(sub_socket, user_name):
    """Função que roda em background para ouvir mensagens do Pub/Sub."""
    print(f"✅ Audição iniciada para o usuário '{user_name}'. Inscrito no seu tópico pessoal.")
    while True:
        try:
            full_message = sub_socket.recv_string()
            topic, payload = full_message.split(' ', 1)
            message_data = json.loads(payload)
            
            sys.stdout.write('\r' + ' ' * 80 + '\r')
            
            if 'from' in message_data:
                print(f"\n📩 [Mensagem de {message_data['from']}]: {message_data['message']}")
            else:
                print(f"\n📢 [{topic}] {message_data['user']}: {message_data['message']}")
            
            sys.stdout.write(f"[{user_name}] Digite uma opção: ")
            sys.stdout.flush()
        except zmq.ZMQError as e:
            print(f"\n[ERRO DE AUDIÇÃO] Conexão perdida: {e}")
            break

# --- CONFIGURAÇÃO ---
REQ_BROKER_URL = "tcp://localhost:5555"
SUB_PROXY_URL = "tcp://localhost:5557"

context = zmq.Context()
req_socket = context.socket(zmq.REQ)
req_socket.connect(REQ_BROKER_URL)
sub_socket = context.socket(zmq.SUB)
sub_socket.connect(SUB_PROXY_URL)

user_nome = input("Digite seu nome de usuário para começar: ")
sub_socket.setsockopt_string(zmq.SUBSCRIBE, user_nome)

listener_thread = threading.Thread(target=message_listener, args=(sub_socket, user_nome), daemon=True)
listener_thread.start()

time.sleep(0.5)
opcao = ""
while opcao != "sair":
    opcao = input(f"[{user_nome}] Digite uma opção (ou 'ajuda'): ").lower()

    match opcao:
        case "ajuda":
            print("\n--- MENU DE OPÇÕES ---\n"
                  "adicionar_user   - Adiciona um novo usuário\n"
                  "adicionar_canal  - Adiciona um novo canal\n"
                  "listar_user      - Lista todos os usuários\n"
                  "listar_canais    - Lista todos os canais\n"
                  "inscrever [canal] - Inscreve você em um canal\n"
                  "publicar [canal]  - Publica uma mensagem em um canal\n"
                  "mensagem [user]   - Envia uma mensagem direta para um usuário\n"
                  "sair             - Encerra o cliente\n"
                  "----------------------")
        
        case "adicionar_canal":
            titulo = input("Entre com o nome do canal: ")
            desc = input("Entre com a descrição do canal: ")
            request = {"service": "addChannel", "data": {"titulo": titulo, "desc": desc}}
            req_socket.send_json(request)
            reply = req_socket.recv_string()
            if reply == "OK":
                print("\n✅ Canal adicionado com sucesso!")
            else:
                print(f"\n❌ {reply}")

        case "adicionar_user":
            user = input("Entre com o nome de usuário: ")
            senha = input("Entre com a senha: ")
            request = {"service": "addUser", "data": {"user": user, "senha": senha}}
            req_socket.send_json(request)
            reply = req_socket.recv_string()
            if reply == "OK":
                print("\n✅ Usuário adicionado com sucesso!")
            else:
                print(f"\n❌ {reply}")
            
        case cmd if cmd.startswith("inscrever"):
            try:
                _, nome_canal = cmd.split()
                sub_socket.setsockopt_string(zmq.SUBSCRIBE, nome_canal.lower())
                print(f"✅ Inscrito com sucesso no canal '{nome_canal.lower()}'")
            except ValueError:
                print("❌ Comando inválido. Use: inscrever <nome_do_canal>")

        case cmd if cmd.startswith("publicar"):
            try:
                _, nome_canal = cmd.split()
                msg_para_enviar = input(f"Mensagem para o canal '{nome_canal}': ")
                timestamp = datetime.datetime.now().isoformat()
                request = {"service": "publish", "data": {"user": user_nome, "channel": nome_canal, "message": msg_para_enviar, "timestamp": timestamp}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                if reply['data']['status'] == 'OK':
                    print("✅ Mensagem enviada para o servidor.")
                else:
                    print(f"❌ Erro: {reply['data']['message']}")
            except ValueError:
                print("❌ Comando inválido. Use: publicar <nome_do_canal>")

        case cmd if cmd.startswith("mensagem"):
            try:
                _, user_destino = cmd.split()
                msg_para_enviar = input(f"Mensagem para '{user_destino}': ")
                timestamp = datetime.datetime.now().isoformat()
                request = {"service": "message", "data": {"src": user_nome, "dst": user_destino, "message": msg_para_enviar, "timestamp": timestamp}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                if reply['data']['status'] == 'OK':
                    print("✅ Mensagem enviada para o servidor.")
                else:
                    print(f"❌ Erro: {reply['data']['message']}")
            except ValueError:
                print("❌ Comando inválido. Use: mensagem <usuario_destino>")

        case "listar_user":
            req_socket.send_json({"service": "listUsers", "data": {}})
            users = req_socket.recv_json()
            print("\n--- Usuários Disponíveis ---")
            for uid, uinfo in users.items():
                print(f" -> {uinfo['user']}")
            print("--------------------------")
        
        case "listar_canais":
            req_socket.send_json({"service": "listChannels", "data": {}})
            canais = req_socket.recv_json()
            print("\n--- Canais Disponíveis ---")
            for cid, cinfo in canais.items():
                print(f" -> {cinfo['titulo']}")
            print("------------------------")
            
        case "sair":
            print("Encerrando...")
            break
            
        case _:
            if opcao:
                print("Opção inválida. Digite 'ajuda' para ver os comandos.")

print("\nCliente encerrado. Até logo!")