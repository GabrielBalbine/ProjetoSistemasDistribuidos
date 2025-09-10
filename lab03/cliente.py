import zmq

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5555")

opcao = input("Entre com a opção: ")
while opcao != "sair":
    match opcao:
        case "adicionar_user":
            user = input("Entre com o nome de usuário: ")
            senha = input("Entre com a senha de usuário: ")

            request = {
                "opcao": "adicionar_user",
                "dados": {
                    "user": user,
                    "senha": senha
                }
            }

            socket.send_json(request)
            reply = socket.recv_string()

            if reply == "OK": #importante, vide codigo servidor
                print("\nUsuario Adicionado com Sucesso")

            #if reply.split(":")[0] == "ERRO":
                #print(reply, flush=True)
            else:
                print(f"\n {reply}\n", flush = True)


        case "adicionar_canal":
            titulo = input("Entre com o nome do canal: ")
            descricao = input("Entre com a descricao do canal: ")

            request = {
                "opcao": "adicionar_canal",
                "dados": {
                    "titulo": titulo,
                    "desc": descricao
                }
            }

            socket.send_json(request)
            reply = socket.recv_string()

            if reply == "OK": #importante, vide codigo servidor
                print("\nUsuario Adicionado com Sucesso")

            #if reply.split(":")[0] == "ERRO":
                #print(reply, flush=True)
            else:
                print(f"\n {reply}\n", flush = True)

        case "atualizar":
            id_para_atualizar = input("Digite o ID da tarefa que deseja atualizar: ")
            novo_titulo = input(f"Digite o NOVO título da tarefa")
            nova_desc = input(f"Digite a NOVA descrição da tarefa")

            #monta request dnv
            request = {
                "opcao":"atualizar",
                "dados": {
                    "id": id_para_atualizar,
                    "novos_dados":{
                        "titulo": novo_titulo,
                        "desc": nova_desc
                    }
                }
            }

            socket.send_json(request)

            #recebe e mostra a resposta
            reply = socket.recv_string()

            if reply == "OK":
                print(f"\nTarefa {id_para_atualizar} atualizada com sucesso!\n")
            else:
                print(f"\n{reply}\n", flush=True)
        case "deletar":
            # pergunta qual tarefa quer remover
            id_pra_remover = input("Digite o ID da tarefa que quer remover:")
            #monta a requisição com o ID
            request = {
                "opcao":"deletar",
                "dados":{
                    "id":id_pra_remover
                }
            }

            socket.send_json(request)

            # recebe e mostra a resposta
            reply = socket.recv_string()

            if reply == "OK":
                print(f"\nTarefa com ID {id_pra_remover} removida com sucesso!\n")
            else:
                print(f"\n{reply}\n", flush = True)
            
        case "listar_user":
        #montando requisicao, dados vazios por consistencia
            request = {
                "opcao":"listar_user",
                "dados":{}
            }
            print("\nBuscando usuários no servidor...")
            socket.send_json(request)

            #recebe usuario
            lista_de_users = socket.recv_json()

            #exibe as respostas
            print("---Lista de Usuários---")
            if not lista_de_users:
                print("Nenhuma tarefa encontrada.")
            else:
                for id, users in lista_de_users.items():
                    print(f" ID: {id}")
                    print(f" Usuário: {users['user']}")
                    print(f" Senha: {users['senha']}")
                    print("-"*20)
                print("--------------------\n")


        case "listar_canais":
        #montando requisicao, dados vazios por consistencia
            request = {
                "opcao":"listar_canais",
                "dados":{}
            }
            print("\nBuscando canais no servidor")
            socket.send_json(request)

            #recebe canal
            lista_de_canais = socket.recv_json()

            #exibe as respostas
            print("---Lista de Canais---")
            if not lista_de_canais:
                print("Nenhum canal encontrado.")
            else:
                for id, canal in lista_de_canais.items():
                    print(f" ID: {id}")
                    print(f" Titulo: {canal['titulo']}")
                    print(f" Descricao: {canal['desc']}")
                    print("-"*20)
                print("--------------------\n")

        case "buscar":
            termo = input("Digite o termo que deseja buscar no título ou na descrição:")

            #monta a requisicao com o termo da busca
            request = {
                "opcao":"buscar",
                "dados": {
                    "termo":termo
                }
            }
            print(f"\nBuscando por '{termo}'...")
            socket.send_json(request)

            #recebe a listinha de results
            resultados_busca = socket.recv_json()

            #exibe os resultados, igual o listar
            print(f"--- Resultados da Busca por '{termo}' ---")
            if not resultados_busca:
                print("Nenhuma tarefa encontrada com este termo")
            else:
                for id, tarefa in resultados_busca.items():
                    print(f" ID: {id}")
                    print(f" Titulo:{tarefa['titulo']}")
                    print(f" Descricao: {tarefa['desc']}")
                    print("-"*20)
                    print("------------------------------\n")
        case _:
            print("Opção não encontrada")

    opcao = input("Entre com a opção: ")
