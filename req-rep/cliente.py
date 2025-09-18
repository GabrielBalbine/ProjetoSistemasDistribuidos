import zmq
import datetime
import threading
import json
import sys
import time
import getpass # Para esconder a senha

def message_listener(sub_socket, user_name):
    """Função que roda em background para ouvir mensagens do Pub/Sub."""
    print(f"\n✅ Audição iniciada para o usuário '{user_name}'. Você receberá mensagens aqui.")
    while True:
        try:
            full_message = sub_socket.recv_string()
            topic, payload = full_message.split(' ', 1)
            message_data = json.loads(payload)
            sys.stdout.write('\r' + ' ' * 80 + '\r')
            if 'from' in message_data:
                print(f"📩 [Mensagem de {message_data['from']}]: {message_data['message']}")
            else:
                print(f"📢 [{topic}] {message_data['user']}: {message_data['message']}")
            sys.stdout.write(f"[{user_name}] Digite uma opção: ")
            sys.stdout.flush()
        except zmq.ZMQError as e:
            print(f"\n[ERRO DE AUDIÇÃO] Conexão perdida: {e}")
            break

def main_app(user_nome, session_token, req_socket, sub_socket):
    """Função principal da aplicação, executada após o login."""
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
                      "listar_user      - Lista todos os usuários\n"
                      "listar_canais    - Lista todos os canais\n"
                      "add_canal        - Adiciona um novo canal\n"
                      "inscrever [canal] - Inscreve você em um canal\n"
                      "publicar [canal]  - Publica uma mensagem em um canal\n"
                      "mensagem [user]   - Envia uma mensagem direta para um usuário\n"
                      "sair             - Desloga e encerra o cliente\n"
                      "----------------------")
            
            case "add_canal":
                titulo = input("Entre com o nome do canal: ")
                desc = input("Entre com a descrição do canal: ")
                request = {"service": "addChannel", "data": {"token": session_token, "titulo": titulo, "desc": desc}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                if reply.get("status") == "OK":
                    print("\n✅ Canal adicionado com sucesso!")
                else:
                    print(f"\n❌ {reply.get('message')}")

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
                    request = {"service": "publish", "data": {"token": session_token, "channel": nome_canal, "message": msg_para_enviar, "timestamp": timestamp}}
                    req_socket.send_json(request)
                    reply = req_socket.recv_json()
                    if reply.get('data', {}).get('status') == 'OK':
                        print("✅ Mensagem enviada para o servidor.")
                    else:
                        print(f"❌ Erro: {reply.get('data', {}).get('message')}")
                except ValueError:
                    print("❌ Comando inválido. Use: publicar <nome_do_canal>")

            case cmd if cmd.startswith("mensagem"):
                try:
                    _, user_destino = cmd.split()
                    msg_para_enviar = input(f"Mensagem para '{user_destino}': ")
                    timestamp = datetime.datetime.now().isoformat()
                    request = {"service": "message", "data": {"token": session_token, "dst": user_destino, "message": msg_para_enviar, "timestamp": timestamp}}
                    req_socket.send_json(request)
                    reply = req_socket.recv_json()
                    if reply.get('status') == 'OK':
                        print("✅ Mensagem enviada para o servidor.")
                    else:
                        print(f"❌ Erro: {reply.get('message')}")
                except ValueError:
                    print("❌ Comando inválido. Use: mensagem <usuario_destino>")

            case "listar_user":
                req_socket.send_json({"service": "listUsers", "data": {}})
                users = req_socket.recv_json()
                print("\n--- Usuários Cadastrados ---")
                for uid, uinfo in users.items():
                    print(f" -> {uinfo['user']}")
                print("----------------------------")
            
            case "listar_canais":
                req_socket.send_json({"service": "listChannels", "data": {}})
                canais = req_socket.recv_json()
                print("\n--- Canais Disponíveis ---")
                for cid, cinfo in canais.items():
                    print(f" -> {cinfo['titulo']}")
                print("------------------------")
                
            case "sair":
                print("Deslogando e encerrando...")
                break
                
            case _:
                if opcao:
                    print("Opção inválida. Digite 'ajuda' para ver os comandos.")

if __name__ == "__main__":
    context = zmq.Context()
    req_socket = context.socket(zmq.REQ)
    req_socket.connect("tcp://localhost:5555")
    
    while True:
        print("\n--- BEM-VINDO ---")
        print("1. Login")
        print("2. Cadastrar novo usuário")
        print("3. Sair")
        choice = input("Escolha uma opção: ")

        if choice == '1':
            user = input("Usuário: ")
            senha = getpass.getpass("Senha: ") # getpass esconde a senha
            request = {"service": "login", "data": {"user": user, "senha": senha}}
            req_socket.send_json(request)
            reply = req_socket.recv_json()
            if reply.get("status") == "OK":
                print("✅ Login realizado com sucesso!")
                # Inicia a aplicação principal após o login
                sub_socket = context.socket(zmq.SUB)
                sub_socket.connect("tcp://localhost:5557")
                main_app(reply.get("user"), reply.get("token"), req_socket, sub_socket)
                break # Sai do loop de login/cadastro
            else:
                print(f"❌ Falha no login: {reply.get('message')}")

        elif choice == '2':
            user = input("Digite o novo nome de usuário: ")
            senha = getpass.getpass("Digite a nova senha: ")
            request = {"service": "addUser", "data": {"user": user, "senha": senha}}
            req_socket.send_json(request)
            reply = req_socket.recv_string()
            if reply == "OK":
                print("\n✅ Usuário cadastrado com sucesso! Agora você pode fazer o login.")
            else:
                print(f"\n❌ {reply}")
        
        elif choice == '3':
            break
        
        else:
            print("Opção inválida.")
            
    print("\nPrograma encerrado. Até logo!")