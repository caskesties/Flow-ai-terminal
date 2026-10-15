# Flow AI Terminal v3

Painel móvel de fluxo experimental para WIN, GC e MGC. Barra verde compradora à esquerda e vermelha vendedora à direita; leitura por 1, 5, 15, 30 minutos e dia (janelas parciais sinalizadas); delta, volume, negócios/s e score de regras.

## Estratégia experimental
Monitoramento configurável do nível 132.480 no WIN, pré-alerta de agressão, confirmação por deslocamento e rompimento, alerta de falso rompimento e invalidação. Stop ilustrativo com bloqueio quando superior a 200 pontos WIN; alvos WIN ilustrativos 300/400 pontos. Para GC/MGC as unidades são diferentes; não se aplicam os 200 pontos do WIN.

## Fontes
DEMO usa dados inventados; CSV de negócios exige timestamp,price,size,side,symbol. Replay é acelerado e não é backtest fiel. WSS recebe JSON equivalente de servidor privado autorizado, sem credenciais no navegador. GC e MGC são fluxos próprios. Módulo anterior gold.html preservado.

## Limitações
Não há IA treinada nem conectividade efetiva a dados CME, B3, NinjaTrader ou Profit. Não é possível identificar nominalmente bancos, ICEBERG ou spoofing a partir de negócios públicos. Score não é taxa de acerto. Requer licenças e servidor, validação histórica fora da amostra, latência, deduplicação, slippage e custos; não executa ordens. No iPhone WebSocket pode suspender em background.
