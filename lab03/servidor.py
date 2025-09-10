import zmq

context = zmq.Context()
socket = context.socket(zmq.REP)
socket.connect("tcp://broker:5556")

users = dict()
canais = dict()
tarefas = dict()
cont = 0

while True:
    request = socket.recv_json()
    opcao = request["opcao"]
    dados = request["dados"]
    reply = "ERRO: função não escolhida"

    match opcao:
        case "adicionar_user":
            users[cont] = dados
            cont += 1
            reply = "OK"

        case "adicionar_canal":
            canais[cont] = dados
            cont += 1
            reply = "OK"

        case "atualizar":
            id_str = dados.get("id")
            novos_dados = dados.get("novos_dados") #dicionario de novos dados
            reply = "ERRO: Dados inválidos ou ID não fornecido."

            if id_str and novos_dados:
                try:
                    id_para_atualizar = int(id_str)

                    #verificamos a existencia do id
                    if id_para_atualizar in tarefas:
                        #se existe, atualizamos
                        tarefas[id_para_atualizar].update(novos_dados)
                        reply = "OK"
                        print(f"Tarefa {id_para_atualizar} atualizada.")
                    
                    else:
                        reply = "ERRO: Tarefa com ID nao encontrado"
                    
                except (ValueError, TypeError):
                    #se a conversao do int ou do id der b.o
                    print(f"Tentativa de atualização falha com dados inválidos: {dados}")
                    reply = "ERRO: Formato inválido"


        case "deletar":
            #get pega de forma segura
            id_str = dados.get("id")
            reply = "ERRO: ID inválido ou não fornecido."

            #verifica a existencia desse ID
            if id_str:
                try:
                    id_para_deletar = int(id_str)

                    if id_para_deletar in tarefas:
                        del tarefas[id_para_deletar] #se existia, nao existe mais
                        reply = "OK"
                    else:
                        reply = "ERRO: Tarefa com este ID não encontrada"
                
                except ValueError:
                    #se int(id_str) falhar, o erro tá definido
                    print(f"Tentativa de remoção com ID inválido: {id_str}")

        case "listar_user":
            print("Enviando a lista de usuario:...")
            reply = users
            socket.send_json(reply)
            continue

        case "listar_canais":
            print("Enviando a lista de canais:...")
            reply = canais
            socket.send_json(reply)
            continue

        case "buscar":
            termo_busca = dados.get("termo","").lower() #pega o termo e converte para minuscula
            resultados = {} #dicionario pra guardar oq foi encontrado

            if termo_busca: #busca caso exista né
                #itera os ids da tarefa
                for id_tarefa, info_tarefa in tarefas.items():
                    titulo = info_tarefa.get("titulo","").lower()
                    desc = info_tarefa.get("desc","").lower()

                    #verifica se o termo ta no titulo ou na descricao
                    if termo_busca in titulo or termo_busca in desc:
                        resultados[id_tarefa] = info_tarefa #adiciona ela ao resultado

            print(f"Busca por '{termo_busca}' encontrou {len(resultados)} resultado(s)")
            #envia os resultados, que podem estar vazios na real
            socket.send_json(resultados)
            continue #pula o send string no fim do loop ali

        case _ :
            reply = "ERRO: função não encontrada"

    socket.send_string(reply)
