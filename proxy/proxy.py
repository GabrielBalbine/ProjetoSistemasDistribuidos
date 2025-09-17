import zmq

# Proxy para Publisher-Subscriber
# XSUB (backend) escuta os publishers (nosso servidor) na porta 5558
# XPUB (frontend) envia para os subscribers (nossos clientes) na porta 5557
context = zmq.Context()
backend = context.socket(zmq.XSUB)
frontend = context.socket(zmq.XPUB)
backend.bind("tcp://*:5558")
frontend.bind("tcp://*:5557")

print("Proxy PUB/SUB iniciado (XSUB:5558, XPUB:5557)")
zmq.proxy(frontend, backend)

backend.close()
frontend.close()
context.close()