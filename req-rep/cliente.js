// cliente_completo.js (CommonJS) - versão compatível com servidor corrigido
const zmq = require("zeromq");
const prompt = require("prompt-sync")({ sigint: true });
const { setTimeout } = require("timers/promises");

// Endereços
const REQ_ADDR = "tcp://broker:5555";
const SUB_ADDR = "tcp://proxy:5557";
let subSocket = null;

// Lamport clock
let lamportClock = 0;
function incClock() { lamportClock++; return lamportClock; }
function updateClock(received) { lamportClock = Math.max(lamportClock, Number(received) || 0) + 1; return lamportClock; }

// Estado do cliente
let currentUser = null;
let sessionToken = null;
let isBot = false;

// Listener assíncrono de mensagens
async function messageListener(userName, autoSubscribe = false) {
  subSocket = new zmq.Subscriber();
  subSocket.connect(SUB_ADDR);
  subSocket.subscribe(userName); // sempre recebe DMs

  if (autoSubscribe) {
    console.log("🤖 Bot detectado: inscrito em todos os canais por padrão.");
  }

  for await (const [topicBuf, msgBuf] of subSocket) {
    try {
      const topic = topicBuf.toString();
      const payload = JSON.parse(msgBuf.toString());
      const receivedLamport = payload.lamport_clock || 0;
      updateClock(receivedLamport);

      process.stdout.write('\r' + ' '.repeat(80) + '\r');
      if (payload.from) {
        console.log(`📩 [DM de ${payload.from}]: ${payload.message}`);
      } else if (payload.user) {
        console.log(`📢 [${topic}] ${payload.user}: ${payload.message}`);
      } else {
        console.log(`🔔 [${topic}] ${JSON.stringify(payload)}`);
      }
      process.stdout.write(`[${userName}] > `);
    } catch (_) {}
  }
}

// Função helper para enviar requests via REQ/REP
async function sendRequest(reqSocket, service, data = {}) {
  incClock();
  const request = { service, data: { ...data, lamport_clock: lamportClock } };
  await reqSocket.send(JSON.stringify(request));
  const [replyBuf] = await reqSocket.receive();
  let reply = {};
  try {
    reply = JSON.parse(replyBuf.toString());
  } catch {
    reply = replyBuf.toString();
  }
  updateClock(reply.lamport_clock || 0);
  return reply;
}

// Menu principal (login e registro)
async function main() {
  const reqSocket = new zmq.Request();
  reqSocket.connect(REQ_ADDR);

  while (true) {
    console.log("\n--- CLIENTE INTERATIVO ---");
    console.log("1. Login");
    console.log("2. Cadastrar novo usuário");
    console.log("3. Sair");
    const choice = prompt("Escolha: ");

    incClock();
    let request = { data: { lamport_clock: lamportClock } };

    if (choice === '1' || choice === '2') {
      request.data.user = prompt("Usuário: ");
      request.data.senha = prompt("Senha: ", { echo: '' });
      request.service = choice === '1' ? 'login' : 'addUser';

      try {
        await reqSocket.send(JSON.stringify(request));
        const [replyBuf] = await reqSocket.receive();
        const res = JSON.parse(replyBuf.toString());
        updateClock(res.lamport_clock || 0);

        if (choice === '1') {
          if (res.status === "OK") {
            console.log("✅ Login realizado com sucesso!");
            currentUser = res.user;
            sessionToken = res.token;
            isBot = currentUser.startsWith("bot-");
            messageListener(currentUser, isBot).catch(e => console.error("Listener error:", e));
            await mainApp(currentUser, sessionToken, reqSocket);
            break;
          } else console.log(`❌ Falha: ${res.message}`);
        } else {
          if (res.status === "OK") console.log("✅ Usuário cadastrado! Faça login agora.");
          else console.log(`❌ ${res.message}`);
        }
      } catch (e) {
        console.error("Erro na comunicação com o servidor:", e);
      }

    } else if (choice === '3') {
      console.log("Saindo...");
      process.exit(0);
    } else {
      console.log("Opção inválida.");
    }
  }
}

// Função pós-login
async function mainApp(user_nome, session_token, reqSocket) {
  await setTimeout(200);

  console.log("\n--- Bem-vindo ao sistema ---");
  console.log("Digite 'ajuda' para ver os comandos disponíveis.\n");

  while (true) {
    const opcao = prompt(`[${user_nome}] > `);
    if (!opcao) continue;
    const [command, ...args] = opcao.toLowerCase().split(' ');

    incClock();
    let request = { data: { token: session_token, user: user_nome, lamport_clock: lamportClock } };

    if (command === 'sair') {
      console.log("👋 Encerrando...");
      process.exit(0);

    } else if (command === 'ajuda') {
      console.log("\nComandos disponíveis:");
      console.log("listar_canais            - Lista canais");
      console.log("listar_user              - Lista usuários");
      console.log("add_canal                - Cria novo canal");
      console.log("inscrever <canal>        - Inscreve-se num canal");
      console.log("publicar <canal>         - Publica mensagem num canal inscrito");
      console.log("mensagem <user>          - Envia mensagem direta");
      console.log("sync_time                - Sincroniza relógio");
      console.log("sair                     - Fecha o cliente");
      console.log("ajuda                    - Mostra este menu\n");

    } else if (command === 'listar_canais' || command === 'listar_user' || command === 'sync_time') {
      request.service = command === 'listar_canais' ? 'listChannels' :
                        command === 'listar_user' ? 'listUsers' : 'getTime';

      try {
        const res = await sendRequest(reqSocket, request.service, request.data);
        if (command === 'listar_canais') {
          console.log("\n--- Canais ---");
          Object.values(res).forEach(c => c.titulo && console.log("→", c.titulo));
        } else if (command === 'listar_user') {
          console.log("\n--- Usuários ---");
          Object.values(res).forEach(u => u.user && console.log("→", u.user));
        } else {
          console.log("\n--- Relógio ---");
          console.log(`Servidor: ${res.server_time_utc}`);
          console.log(`Local:    ${new Date().toISOString()}`);
        }
      } catch (e) { console.error("Erro:", e); }

    } else if (command === 'add_canal') {
      request.service = 'addChannel';
      request.data.titulo = prompt("Nome do canal: ").toLowerCase();
      request.data.desc = prompt("Descrição: ");
      const res = await sendRequest(reqSocket, 'addChannel', request.data);
      if (res.status === "OK") {
        console.log("✅ Canal criado!");
        // bots se inscrevem automaticamente
        if (isBot && subSocket) subSocket.subscribe(request.data.titulo);
      } else console.log("❌", res.message);

    } else if (command === 'inscrever') {
      const canal = args[0];
      if (!canal) return console.log("❌ Use: inscrever <canal>");
      const res = await sendRequest(reqSocket, 'subscribe', { ...request.data, channel: canal });
      if (res.status === "OK") {
        console.log(`✅ ${res.message}`);
        if (subSocket) subSocket.subscribe(canal);
      } else console.log(`❌ ${res.message}`);

    } else if (command === 'publicar') {
      const canal = args[0];
      if (!canal) return console.log("❌ Use: publicar <canal>");
      const mensagem = prompt("Mensagem: ");
      const res = await sendRequest(reqSocket, 'publish', {
        ...request.data,
        channel: canal,
        message: mensagem,
        timestamp: new Date().toISOString()
      });
      if (res.status === "OK") console.log("✅ Mensagem publicada!");
      else console.log("❌", res.message);

    } else if (command === 'mensagem') {
      const dst = args[0];
      if (!dst) return console.log("❌ Use: mensagem <user>");
      const mensagem = prompt("Mensagem: ");
      const res = await sendRequest(reqSocket, 'message', {
        ...request.data,
        dst,
        message: mensagem,
        timestamp: new Date().toISOString()
      });
      if (res.status === "OK") console.log("✅ Mensagem enviada!");
      else console.log("❌", res.message);

    } else {
      console.log("Comando inválido. Digite 'ajuda'.");
    }
  }
}

// Início
main().catch(e => console.error("Erro fatal:", e));
