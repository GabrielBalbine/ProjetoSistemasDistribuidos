// req-rep/cliente.js

const zmq = require("zeromq");
const prompt = require("prompt-sync")({ sigint: true });

let subSocket; // Declarado globalmente para ser acessado por múltiplas funções

async function messageListener(userName) {
    console.log(`\n✅ Audição iniciada para o usuário '${userName}'. Você receberá mensagens aqui.`);
    subSocket = new zmq.Subscriber();
    subSocket.connect("tcp://proxy:5557");
    subSocket.subscribe(userName);

    for await (const [topic, msg] of subSocket) {
        try {
            const payload = JSON.parse(msg.toString());
            process.stdout.write('\r' + ' '.repeat(80) + '\r');
            if (payload.from) {
                console.log(`📩 [Mensagem de ${payload.from}]: ${payload.message}`);
            } else {
                console.log(`📢 [${topic.toString()}] ${payload.user}: ${payload.message}`);
            }
            process.stdout.write(`[${userName}] Digite uma opção: `);
        } catch (e) {
            // Ignora mensagens que não são JSON válidas
        }
    }
}

async function main() {
    const reqSocket = new zmq.Request();
    reqSocket.connect("tcp://broker:5555");
    
    let userName = null;
    let sessionToken = null;

    while (true) {
        console.log("\n--- BEM-VINDO (Cliente Node.js) ---");
        console.log("1. Login");
        console.log("2. Cadastrar novo usuário");
        console.log("3. Sair");
        const choice = prompt("Escolha uma opção: ");

        if (choice === '1') {
            const user = prompt("Usuário: ");
            const pass = prompt("Senha: ", { echo: '' }); // Sem echo para esconder a senha
            
            await reqSocket.send(JSON.stringify({ service: "login", data: { user: user, senha: pass } }));
            const [reply] = await reqSocket.receive();
            const res = JSON.parse(reply.toString());
            
            if (res.status === "OK") {
                console.log("✅ Login realizado com sucesso!");
                userName = res.user;
                sessionToken = res.token;
                break;
            } else {
                console.log(`❌ Falha no login: ${res.message}`);
            }
        } else if (choice === '2') {
            const user = prompt("Digite o novo nome de usuário: ");
            const pass = prompt("Digite a nova senha: ", { echo: '' });
            await reqSocket.send(JSON.stringify({ service: "addUser", data: { user: user, senha: pass } }));
            const [reply] = await reqSocket.receive();
            if (reply.toString() === "OK") {
                console.log("\n✅ Usuário cadastrado com sucesso! Agora você pode fazer o login.");
            } else {
                console.log(`\n❌ ${reply.toString()}`);
            }
        } else if (choice === '3') {
            console.log("Encerrando...");
            await reqSocket.close();
            process.exit(0);
        } else {
            console.log("Opção inválida.");
        }
    }
    
    messageListener(userName);
    
    while (true) {
        const input = prompt(`[${userName}] Digite uma opção (ou 'ajuda'): `);
        const [command, ...args] = input.toLowerCase().split(' ');
        
        if (command === 'sair') {
            console.log("Deslogando e encerrando...");
            await reqSocket.close();
            subSocket.close();
            process.exit(0);
        } else if (command === 'ajuda') {
            console.log("\n--- Comandos Disponíveis ---\n" +
                        "listar_canais    - Lista todos os canais\n" +
                        "add_canal        - Adiciona um novo canal\n" +
                        "inscrever [canal] - Inscreve você em um canal\n" +
                        "publicar [canal]  - Publica uma mensagem em um canal\n" +
                        "mensagem [user]   - Envia uma mensagem direta\n" +
                        "sair             - Encerra o cliente\n" +
                        "----------------------------");
        } else if (command === 'listar_canais') {
            await reqSocket.send(JSON.stringify({ service: "listChannels", data: {} }));
            const [reply] = await reqSocket.receive();
            const canais = JSON.parse(reply.toString());
            console.log("\n--- Canais Disponíveis ---");
            for (const id in canais) {
                console.log(` -> ${canais[id].titulo}`);
            }
            console.log("------------------------");
        } else if (command === 'add_canal') {
            const titulo = prompt("Nome do novo canal: ");
            const desc = prompt("Descrição do canal: ");
            const request = { service: "addChannel", data: { token: sessionToken, titulo, desc } };
            await reqSocket.send(JSON.stringify(request));
            const [reply] = await reqSocket.receive();
            const res = JSON.parse(reply.toString());
            if (res.status === "OK") console.log("✅ Canal adicionado com sucesso!");
            else console.log(`❌ Erro: ${res.message}`);
        } else if (command === 'inscrever') {
            const channelName = args[0];
            if (!channelName) console.log("❌ Use: inscrever <nome_do_canal>");
            else {
                subSocket.subscribe(channelName);
                console.log(`✅ Inscrito com sucesso no canal '${channelName}'`);
            }
        } else if (command === 'publicar') {
            const channelName = args[0];
            if (!channelName) console.log("❌ Use: publicar <nome_do_canal>");
            else {
                const message = prompt(`Mensagem para '${channelName}': `);
                const request = { service: "publish", data: { token: sessionToken, channel: channelName, message, timestamp: new Date().toISOString() } };
                await reqSocket.send(JSON.stringify(request));
                const [reply] = await reqSocket.receive();
                const res = JSON.parse(reply.toString());
                if (res.status === "OK") console.log("✅ Mensagem enviada.");
                else console.log(`❌ Erro: ${res.message}`);
            }
        } else if (command === 'mensagem') {
            const destUser = args[0];
            if (!destUser) console.log("❌ Use: mensagem <usuario_destino>");
            else {
                const message = prompt(`Mensagem para '${destUser}': `);
                const request = { service: "message", data: { token: sessionToken, dst: destUser, message, timestamp: new Date().toISOString() } };
                await reqSocket.send(JSON.stringify(request));
                const [reply] = await reqSocket.receive();
                const res = JSON.parse(reply.toString());
                if (res.status === "OK") console.log("✅ Mensagem enviada.");
                else console.log(`❌ Erro: ${res.message}`);
            }
        } else {
            if (command) console.log("Comando inválido. Digite 'ajuda'.");
        }
    }
}

main();