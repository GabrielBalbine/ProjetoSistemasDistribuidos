const zmq = require("zeromq");
const prompt = require("prompt-sync")({ sigint: true });
const { setTimeout } = require("timers/promises");

let subSocket;
let lamportClock = 0;

async function messageListener(userName) {
    console.log(`\n✅ Audição iniciada para o usuário '${userName}'.`);
    subSocket = new zmq.Subscriber();
    subSocket.connect("tcp://proxy:5557");
    subSocket.subscribe(userName);

    for await (const [topic, msg] of subSocket) {
        try {
            const payload = JSON.parse(msg.toString());
            const receivedLamportClock = payload.lamport_clock || 0;

            lamportClock = Math.max(lamportClock, receivedLamportClock) + 1;
            console.log(`\n[CLOCK] Pub recebida! Clock da msg: ${receivedLamportClock}, meu clock atualizado: ${lamportClock}`);

            process.stdout.write('\r' + ' '.repeat(80) + '\r');
            if (payload.from) {
                console.log(`📩  [Mensagem de ${payload.from}]: ${payload.message}`);
            } else {
                console.log(`📢  [${topic.toString()}] ${payload.user}: ${payload.message}`);
            }
            process.stdout.write(`[${userName}] Digite uma opção: `);
        } catch (e) {
            // Ignore mensagens mal formatadas ou vazias
        }
    }
}

async function mainApp(user_nome, session_token, reqSocket) {
    messageListener(user_nome);
    await setTimeout(500);

    let opcao = "";
    while (opcao !== "sair") {
        opcao = prompt(`[${user_nome}] Digite uma opção (ou 'ajuda'): `);
        if (!opcao) continue;

        const [command, ...args] = opcao.toLowerCase().split(' ');

        lamportClock++;
        let request = { data: { token: session_token, lamport_clock: lamportClock } };

        if (command === 'sair') {
            console.log("Deslogando e encerrando...");
            break;

        } else if (command === 'ajuda') {
            console.log("\n--- MENU DE OPÇÕES ---\n" +
                "listar_canais    - Lista todos os canais\n" +
                "listar_user      - Lista todos os usuários\n" +
                "add_canal       - Adiciona um novo canal\n" +
                "inscrever [canal] - Inscreve você em um canal\n" +
                "publicar [canal]  - Publica uma mensagem em um canal\n" +
                "mensagem [user]   - Envia uma mensagem direta\n" +
                "sync_time        - Compara a hora com o Coordenador\n" +
                "sair             - Encerra o cliente\n" +
                "----------------------");

        } else if (command === 'listar_canais' || command === 'sync_time' || command === 'listar_user') {
            if (command === 'listar_canais') request.service = 'listChannels';
            else if (command === 'listar_user') request.service = 'listUsers';
            else request.service = 'getTime';

            await reqSocket.send(JSON.stringify(request));
            const [reply] = await reqSocket.receive();

            try {
                const res = JSON.parse(reply.toString());

                if (command === 'listar_canais') {
                    console.log("\n--- Canais Disponíveis ---");
                    for (const id in res) console.log(` -> ${res[id].titulo}`);
                    console.log("------------------------");
                } else if (command === 'listar_user') {
                    console.log("\n--- Usuários Cadastrados ---");
                    for (const id in res) console.log(` -> ${res[id].user}`);
                    console.log("----------------------------");
                } else { // sync_time
                    console.log("\n--- Sincronização de Relógio ---");
                    console.log(`Hora do Coordenador (UTC): ${res.server_time_utc}`);
                    console.log(`Sua Hora Local (Cliente):      ${new Date().toISOString()}`);
                    console.log("------------------------------");
                }
                lamportClock = Math.max(lamportClock, res.lamport_clock || 0) + 1;

            } catch (e) {
                console.error("Resposta inesperada do servidor:", reply.toString());
            }

        } else if (command === 'add_canal') {
            request.service = "addChannel";
            request.data.titulo = prompt("Nome do novo canal: ").toLowerCase();
            request.data.desc = prompt("Descrição do canal: ");
            await reqSocket.send(JSON.stringify(request));
            const [reply] = await reqSocket.receive();

            try {
                const res = JSON.parse(reply.toString());
                if (res.status === "OK") console.log("✅ Canal adicionado com sucesso!");
                else console.log(`❌ Erro: ${res.message}`);
                lamportClock = Math.max(lamportClock, res.lamport_clock || 0) + 1;
            } catch (e) {
                console.error("Resposta inesperada do servidor:", reply.toString());
            }

        } else if (command === 'inscrever') {
            const channelName = args[0];
            if (!channelName) console.log("❌ Use: inscrever <nome_do_canal>");
            else {
                subSocket.subscribe(channelName.toLowerCase());
                console.log(`✅ Inscrito com sucesso no canal '${channelName.toLowerCase()}'`);
            }

        } else if (command === 'publicar' || command === 'mensagem') {
            const target = args[0];
            if (!target) {
                console.log(`❌ Use: ${command} <alvo>`);
            } else {
                if (command === 'publicar') {
                    request.service = 'publish';
                    request.data.channel = target.toLowerCase();
                } else { // mensagem
                    request.service = 'message';
                    request.data.dst = target;
                }
                request.data.message = prompt(`Mensagem para '${target}': `);
                request.data.timestamp = new Date().toISOString();

                await reqSocket.send(JSON.stringify(request));
                const [reply] = await reqSocket.receive();

                try {
                    const res = JSON.parse(reply.toString());

                    if (res.status === "OK") {
                        console.log("✅ Mensagem enviada.");
                        lamportClock = Math.max(lamportClock, res.lamport_clock || 0) + 1;
                        console.log(`[CLOCK] Resposta recebida. Meu clock atualizado: ${lamportClock}`);
                    } else {
                        console.log(`❌ Erro: ${res.message}`);
                    }
                } catch (e) {
                    console.error("Resposta inesperada do servidor:", reply.toString());
                }
            }

        } else {
            if (opcao) console.log("Comando inválido. Digite 'ajuda'.");
        }
    }
}

async function start() {
    const reqSocket = new zmq.Request();
    reqSocket.connect("tcp://broker:5555");

    while (true) {
        console.log("\n--- BEM-VINDO (Cliente Node.js) ---");
        console.log("1. Login");
        console.log("2. Cadastrar novo usuário");
        console.log("3. Sair");
        const choice = prompt("Escolha uma opção: ");

        lamportClock++;
        let request = { data: { lamport_clock: lamportClock } };

        if (choice === '1' || choice === '2') {
            request.data.user = prompt("Usuário: ");
            request.data.senha = prompt("Senha: ", { echo: '' }); // senha oculta

            request.service = choice === '1' ? 'login' : 'addUser';
            await reqSocket.send(JSON.stringify(request));
            const [reply] = await reqSocket.receive();

            try {
                const res = JSON.parse(reply.toString());
                lamportClock = Math.max(lamportClock, res.lamport_clock || 0) + 1;

                if (choice === '1') {
                    if (res.status === "OK") {
                        console.log("✅ Login realizado com sucesso!");
                        await mainApp(res.user, res.token, reqSocket);
                        break;
                    } else {
                        console.log(`❌ Falha no login: ${res.message}`);
                    }
                } else { // choice === '2'
                    if (res.status === "OK") {
                        console.log("\n✅ Usuário cadastrado com sucesso! Agora você pode fazer o login.");
                    } else {
                        console.log(`\n❌ ${res.message || res}`);
                    }
                }
            } catch (e) {
                console.error("Resposta inesperada do servidor:", reply.toString());
            }

        } else if (choice === '3') {
            break;

        } else {
            console.log("Opção inválida.");
        }
    }

    console.log("\nPrograma encerrado. Até logo!");
    process.exit(0);
}

start();
