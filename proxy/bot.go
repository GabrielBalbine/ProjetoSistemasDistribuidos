package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"time"

	zmq "github.com/pebbe/zmq4"
)

type ChannelInfo struct{ Titulo string `json:"titulo"` }

func messageListener() {
	log.Println("🎧 Goroutine de audição iniciada.")
	subSocket, _ := zmq.NewSocket(zmq.SUB)
	subSocket.Connect("tcp://proxy:5557")
	subSocket.SetSubscribe("")
	defer subSocket.Close()

	for {
		msgParts, err := subSocket.RecvMessageBytes(0)
		if err != nil {
			continue
		}
		if len(msgParts) >= 2 {
			topic := string(msgParts[0])
			content := string(msgParts[1])
			log.Printf("🎧 [MENSAGEM RECEBIDA] Tópico: %s, Conteúdo: %s", topic, content)
		}
	}
}

func main() {
	log.Println("🤖 Bot em Go iniciado.")
	rand.Seed(time.Now().UnixNano())
	botUserName := fmt.Sprintf("bot-go-%d", rand.Intn(1000))
	log.Printf("Bot identificado como: %s", botUserName)

	go messageListener()

	for {
		reqSocket, _ := zmq.NewSocket(zmq.REQ)
		reqSocket.Connect("tcp://broker:5555")
		
		poller := zmq.NewPoller()
		// CORREÇÃO AQUI: Usando .Add() em vez de .Register()
		poller.Add(reqSocket, zmq.POLLIN)

		log.Println("Buscando lista de canais...")
		reqSocket.Send(`{"service": "listChannels", "data": {}}`, 0)
		
		sockets, err := poller.Poll(5 * time.Second)
		if err != nil || len(sockets) == 0 {
			log.Println("TIMEOUT ou erro ao buscar canais. O líder pode ter mudado. Tentando novamente...")
			reqSocket.Close()
			time.Sleep(5 * time.Second)
			continue
		}
		
		reply, _ := reqSocket.Recv(0)
		
		var channels map[string]ChannelInfo
		json.Unmarshal([]byte(reply), &channels)
		
		if len(channels) == 0 {
			log.Println("Nenhum canal encontrado. Criando canal 'geral'...")
			createRequest := `{"service": "addChannel", "data": {"user": "` + botUserName + `", "titulo": "geral", "desc": "Canal geral criado por bot"}}`
			reqSocket.Send(createRequest, 0)
			
			sockets, err = poller.Poll(5 * time.Second)
			if err != nil || len(sockets) == 0 {
				log.Println("TIMEOUT ao criar canal. Tentando novamente...")
				reqSocket.Close()
				continue
			}
			reqSocket.Recv(0)
			log.Println("Canal 'geral' criado com sucesso. Reiniciando ciclo.")
			reqSocket.Close()
			time.Sleep(2 * time.Second)
			continue
		}

		var channelKeys []string
		for k := range channels { channelKeys = append(channelKeys, k) }
		randomChannelKey := channelKeys[rand.Intn(len(channelKeys))]
		randomChannelName := channels[randomChannelKey].Titulo
		log.Printf("Canal escolhido: '%s'", randomChannelName)

		for i := 0; i < 5; i++ {
			message := fmt.Sprintf("Olá do bot proativo em Go! Mensagem %d/5", i+1)
			
			requestData, _ := json.Marshal(map[string]interface{}{
				"channel": randomChannelName, "message": message, "user": botUserName,
				"timestamp": time.Now().Format(time.RFC3339),
			})
			request := fmt.Sprintf(`{"service": "publish", "data": %s}`, string(requestData))

			reqSocket.Send(request, 0)
			
			sockets, err = poller.Poll(5 * time.Second)
			if err != nil || len(sockets) == 0 {
				log.Printf("TIMEOUT ao enviar mensagem. Abortando lote.")
				break
			}
			publishReply, _ := reqSocket.Recv(0)
			log.Printf(" -> Mensagem enviada para '%s'. Resposta: %s", randomChannelName, publishReply)
			time.Sleep(time.Duration(rand.Intn(2)+1) * time.Second)
		}
		
		reqSocket.Close()
		log.Println("Ciclo concluído. Aguardando...")
		time.Sleep(10 * time.Second)
	}
}