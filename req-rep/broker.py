import zmq

# Broker para Request-Reply
# ROUTER (frontend) escuta os clientes na porta 5555
# DEALER (backend) conversa com os servidores na porta 5556
context = zmq.Context()
frontend = context.socket(zmq.ROUTER)
backend = context.socket(zmq.DEALER)
frontend.bind("tcp://*:5555")
backend.bind("tcp://*:5556")

print("Broker REQ/REP iniciado (ROUTER:5555, DEALER:5556)")
zmq.proxy(frontend, backend)

frontend.close()
backend.close()
context.close()