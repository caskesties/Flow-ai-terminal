# Deploy do backend Flow no Northflank

Este repositório contém o backend da Massive em `backend/`. O `Dockerfile` na raiz permite que o Northflank o construa com contexto `/`, sem mudar as regras de leitura de fluxo.

## Serviço
- Tipo: **Combined Service**, repositório `caskesties/Flow-ai-terminal`, branch `main`.
- Build: **Dockerfile**, caminho `/Dockerfile`, contexto `/`.
- Deploy: **uma réplica apenas**, para evitar WebSockets simultâneos consumindo limite do fornecedor.
- Networking: porta interna **8765**, protocolo **HTTP/1.1 (WebSocket upgrade)**. O domínio público gerado pelo Northflank termina em TLS; conectar pelo **wss://**. Não configurar a porta como raw TCP público.
- Probe: evitar health check HTTP GET em `/` ou `/health`: o processo atende WebSocket, não rotas HTTP. Usar checagem TCP de processo, se disponível, e validar a conexão WSS autenticada separadamente.

## Runtime secrets (nunca gravar no GitHub)
- `MASSIVE_API_KEY`: chave de dados da Massive.
- `FLOW_BRIDGE_TOKEN`: token longo, aleatório, ao menos 24 caracteres.
- `MASSIVE_SYMBOLS`: contratos datados habilitados/verificados junto ao fornecedor (exemplo: `GCZ6,MGCZ6,NQZ6,MNQZ6`; checar rolagem e cobertura).
- `FLOW_BRIDGE_PORT=8765`.

Atenção: o navegador recebe o `FLOW_BRIDGE_TOKEN` para se autenticar; não o confundir com proteção de acesso ao site. O endpoint WebSocket permite acesso com esse segredo: exigir restrições adequadas de origem/acesso e não distribuir o token. A API key da Massive permanece SOMENTE no servidor.

## Validação antes de desativar o Railway
1. Conferir que a implantação está rodando com uma réplica, sem reinicializações repetidas.
2. Ver nos logs `Massive authentication OK`, assinatura dos canais e contagens de negócios/cotações. `max_connections` indica conflitos de sessão; parar a instância antiga antes de conectar o novo provedor.
3. Abrir o painel protegido, configurar `wss://<dominio-do-servico>/market` e token. O backend ignora o caminho, mas espera primeiro uma mensagem JSON autenticada; verificar `ready`, `replay_complete` e `feed_health: LIVE` com negócios classificados do contrato certo.
4. Confirmar os radares de 2/5 minutos e timestamps; validação de juros/ZN e notificações requer dados e testes reais separados.
5. Testar push no iPhone dentro das janelas configuradas; `push_test_result.success` significa tentativa de envio e **não** comprova entrega.
6. Observar estabilidade após bloquear a tela e alternar aplicativos. O WebSocket do navegador pode suspender no iOS; alertas push, quando configurados, precisam sair do backend.
7. Só então trocar a produção. Não rodar dois bridges Massive em paralelo se a conta limitar conexões.

O backend atual ainda é experimental e não executa ordens. Os alertas não são garantia de sinal de mercado nem de rentabilidade.
