package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"time"

	zmq "github.com/pebbe/zmq4"
)

type ChannelInfo struct {
	Titulo string `json:"titulo"`
	Desc   string `json:"desc"`
}

// NOVA FUNÇÃO CORRIGIDA: Roda em paralelo para ouvir mensagens
func messageListener() {
	log.Println("🎧 Goroutine de audição iniciada.")
	subSocket, _ := zmq.NewSocket(zmq.SUB)
	subSocket.Connect("tcp://proxy:5557")
	// O bot se inscreve em TUDO para monitorar a atividade geral
	subSocket.SetSubscribe("")
	defer subSocket.Close()

	for {
		// CORREÇÃO AQUI: Recebemos 2 valores: uma lista de "bytes" e um erro.
		msgParts, err := subSocket.RecvMessageBytes(0)
		if err != nil {
			continue // Ignora erros de recebimento
		}

		// Verificamos se a mensagem tem pelo menos 2 partes (tópico e conteúdo)
		if len(msgParts) >= 2 {
			topic := string(msgParts[0])   // A parte 0 é o tópico
			content := string(msgParts[1]) // A parte 1 é o conteúdo
			log.Printf("🎧 [MENSAGEM RECEBIDA] Tópico: %s, Conteúdo: %s", topic, content)
		}
	}
}

func main() {
	log.Println("🤖 Bot em Go iniciado.")

	// --- Conexão com o Broker REQ/REP ---
	reqSocket, _ := zmq.NewSocket(zmq.REQ)
	reqSocket.Connect("tcp://broker:5555")
	defer reqSocket.Close()

	// INICIA O OUVINTE EM PARALELO!
	go messageListener()

	rand.Seed(time.Now().UnixNano())
	botUserName := fmt.Sprintf("bot-go-%d", rand.Intn(1000))
	log.Printf("Bot identificado como: %s", botUserName)

	for {
		// (O resto do loop de publicação continua exatamente o mesmo...)
		log.Println("Buscando lista de canais...")
		reqSocket.Send(`{"service": "listChannels", "data": {}}`, 0)
		reply, err := reqSocket.Recv(0)
		if err != nil {
			log.Printf("Erro ao receber lista de canais: %v. Tentando novamente em 10s.", err)
			time.Sleep(10 * time.Second)
			continue
		}

		var channels map[string]ChannelInfo
		json.Unmarshal([]byte(reply), &channels)

		if len(channels) == 0 {
			log.Println("Nenhum canal encontrado. Aguardando 10 segundos...")
			time.Sleep(10 * time.Second)
			continue
		}

		var channelKeys []string
		for k := range channels {
			channelKeys = append(channelKeys, k)
		}
		randomChannelKey := channelKeys[rand.Intn(len(channelKeys))]
		randomChannelName := channels[randomChannelKey].Titulo
		log.Printf("Canal escolhido: '%s'", randomChannelName)

		for i := 0; i < 5; i++ { // Diminuí para 5 para não poluir tanto o log
			message := fmt.Sprintf("Olá do bot em Go! Mensagem %d/5", i+1)
			timestamp := time.Now().Format(time.RFC3339)
			
			requestData, _ := json.Marshal(map[string]interface{}{
				"token":     "",
				"channel":   randomChannelName,
				"message":   message,
				"timestamp": timestamp,
				"user":      botUserName,
			})
			request := fmt.Sprintf(`{"service": "publish", "data": %s}`, string(requestData))

			reqSocket.Send(request, 0)
			publishReply, _ := reqSocket.Recv(0)
			log.Printf(" -> Mensagem enviada para '%s'. Resposta: %s", randomChannelName, publishReply)
			time.Sleep(time.Duration(rand.Intn(3)+1) * time.Second)
		}

		log.Println("Lote de mensagens enviado. Aguardando próximo ciclo...")
		time.Sleep(time.Duration(rand.Intn(10)+10) * time.Second)
	}
}