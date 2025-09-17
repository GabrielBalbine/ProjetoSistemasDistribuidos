import zmq

print("Iniciando monitor de tópicos... (Ouvindo tudo)")

context = zmq.Context()
sub_socket = context.socket(zmq.SUB)
sub_socket.setsockopt_string(zmq.SUBSCRIBE, "") 
# Dentro do Docker, nos conectamos usando o nome do serviço
sub_socket.connect("tcp://proxy:5557")

while True:
    message = sub_socket.recv_string()
    print(f"[MONITOR] {message}", flush=True)

sub_socket.close()
context.close()