# Flow AI Terminal v3

Painel móvel de fluxo experimental para WIN, GC e MGC. Barra verde compradora à esquerda e vermelha vendedora à direita; leitura por 1, 5, 15, 30 minutos e dia (janelas parciais sinalizadas); delta, volume, negócios/s e score de regras.

## Estratégia experimental
Monitoramento configurável do nível 132.480 no WIN, pré-alerta de agressão, confirmação por deslocamento e rompimento, alerta de falso rompimento e invalidação. Stop ilustrativo com bloqueio quando superior a 200 pontos WIN; alvos WIN ilustrativos 300/400 pontos. Para GC/MGC as unidades são diferentes; não se aplicam os 200 pontos do WIN.

## Fontes
DEMO usa dados inventados; CSV de negócios exige timestamp,price,size,side,symbol. Replay é acelerado e não é backtest fiel. WSS recebe JSON equivalente de servidor privado autorizado, sem credenciais no navegador. GC e MGC são fluxos próprios. Módulo anterior gold.html preservado.

## Limitações
Não há IA treinada nem conectividade efetiva a dados CME, B3, NinjaTrader ou Profit. Não é possível identificar nominalmente bancos, ICEBERG ou spoofing a partir de negócios públicos. Score não é taxa de acerto. Requer licenças e servidor, validação histórica fora da amostra, latência, deduplicação, slippage e custos; não executa ordens. No iPhone WebSocket pode suspender em background.

## Filtro DI1 e pressão anormal
WIN: feed WSS aceita, além de trades, `{ "symbol":"DI1-...", "timestamp":"2026-10-15T18:00:00Z", "rate":13.25 }` (taxa percentual anual; especificar vencimento consistente). DI1 precisa estar fresco (<3 s) e mudar na direção contrária do WIN em janela de 5s por pelo menos 0,005 ponto percentual; a relação inversa é hipótese e falha em certos regimes. Volume da última janela de 1s comparado à média de 12 segundos anteriores (mínimo 8 janelas com negócios), gatilho >=1,8× e predominância >=55%. Pré-alerta experimental em milissegundos após chegada da mensagem, com objetivo de antecipar 2–3s, mas sem garantia de antecedência ou acerto. Sem DI1, não há pré-alerta WIN por confluência nem confirmação WIN. A simulação DI1 é inteiramente fictícia. CSV de trades isolados NÃO contém DI1, logo não pode satisfazer esse filtro.

## Pré-abertura (estrutura preparada)
Painel de preço teórico, quantidade teórica, desequilíbrio de ofertas e hipótese para abertura. Inicialmente mostra apenas campos indisponíveis — **não** inventa dados nem sinais. Para ativação: validar cobertura da Nelogica para leilão e tipos de mensagens, sessão/horário por instrumento, tratamento de cancelamentos de ofertas e confirmação em negócios executados após abertura. A ferramenta não opera automaticamente.

## Validação de desempenho (pendente)
Registrar sinais, estado do feed, horário, preços, latência, risco e movimento futuro por horizonte; separar testes de ajuste e testes fora da amostra. Medir falsos positivos, taxa de acerto, drawdown, custos e slippage antes de classificar qualquer estratégia como confiável.
