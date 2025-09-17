FROM python:3.9-slim
WORKDIR /app
# Copia tudo da pasta proxy para dentro do contexto de build
COPY . /app/
RUN pip install pyzmq
# O CMD será sobrescrito no docker-compose.yml para cada serviço