import zmq
import datetime
import random
import time
import string
import json

# --- Configuração ---
# Dentro do Docker, nos conectamos usando o nome do serviço
REQ_BROKER_URL = "tcp://broker:5555"
USER_PREFIX = "bot"
MESSAGES_TO_SEND = 10

POSSIBLE_MESSAGES = [
    "Alguém viu a última atualização do projeto?", "O café da máquina nova está bom hoje!",
    "Lembrete: reunião de alinhamento às 15h.", "Quem topa um happy hour na sexta?",
    "Acho que encontrei um bug na API de pagamentos.", "O deploy de ontem foi um sucesso!",
    "Qual o melhor framework para front-end em 2025?", "Preciso de ajuda com um container Docker que não sobe.",
    "A documentação da nova feature já está no Confluence.", "Feliz aniversário para o colega do financeiro!"
]

def get_random_string(length=5):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

context = zmq.Context()
req_socket = context.socket(zmq.REQ)
req_socket.connect(REQ_BROKER_URL)

bot_user_name = f"{USER_PREFIX}-{get_random_string()}"
print(f"🤖 Bot '{bot_user_name}' iniciado.")

while True:
    try:
        req_socket.send_json({"service": "listChannels", "data": {}})
        canais = req_socket.recv_json()

        if not canais:
            print("Nenhum canal encontrado. Aguardando 10 segundos...")
            time.sleep(10)
            continue
        
        random_channel_id = random.choice(list(canais.keys()))
        random_channel_name = canais[random_channel_id]['titulo']
        print(f"Canal escolhido: '{random_channel_name}'")

        for i in range(MESSAGES_TO_SEND):
            message = random.choice(POSSIBLE_MESSAGES)
            timestamp = datetime.datetime.now().isoformat()
            
            request = {
                "service": "publish",
                "data": {"user": bot_user_name, "channel": random_channel_name, "message": f"{message} ({i+1}/{MESSAGES_TO_SEND})", "timestamp": timestamp}
            }
            req_socket.send_json(request)
            reply = req_socket.recv_json()
            print(f" -> Mensagem enviada para '{random_channel_name}'. Status: {reply['data']['status']}")
            time.sleep(random.uniform(0.5, 2.0))

        print(f"Lote de {MESSAGES_TO_SEND} mensagens enviado. Aguardando próximo ciclo...")
        time.sleep(random.uniform(5, 15))

    except zmq.ZMQError as e:
        print(f"Erro de conexão ZMQ: {e}. Tentando reconectar em 5 segundos...")
        req_socket.close()
        req_socket = context.socket(zmq.REQ)
        req_socket.connect(REQ_BROKER_URL)
        time.sleep(5)
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        time.sleep(10)