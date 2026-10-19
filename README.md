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

## Melhorias anti-falso-sinal (outubro 2026)
- Sem implementar módulo de leilão nesta etapa.
- Requer sincronia WIN-DI1 de até 1500 ms e DI1 recente; dados ausentes bloqueiam confluência.
- Requer volume >=60 e velocidade >=2 negócios/s na janela de 60s, evita lacunas >2s, rejeita duplicatas quando o fornecedor disponibiliza `trade_id`/`id`. Limites são provisórios e exigem calibração; dados sem id ainda dependem de deduplicação no backend.
- Pressão fora do normal é estimada por comparação com 12s anteriores; **comparação com sessões anteriores no mesmo horário ainda não é possível** sem base histórica persistente. Esse mecanismo não deve ser anunciado como sazonalidade validada.
- Registra alertas em localStorage e movimento bruto após 5s/30s em modo demo/WSS enquanto a tela está aberta. Não é backtest, não calcula taxa de acerto confiável e não funciona em background.

## Detector de absorção (experimental)
No painel principal aparece uma região baseada em 12 segundos de negócios: agressão líquida relevante (>48% do volume), volume mínimo de 100 contratos, baixo deslocamento (até 3 ticks) e pelo menos quatro negócios na extremidade testada. Uma região tem bordas de ±1 tick, é exibida enquanto permanece ativa e marcada como rompida quando o preço ultrapassa uma borda com um tick adicional. O rompimento gera alerta **sem recomendar entrada**, aguardando confirmação de fluxo/DI1/risco. Todos os limiares são ilustrativos e exigem calibração para cada mercado. Sem livro de ofertas não é possível afirmar absorção institucional real, nem inferir ordens ocultas ou identidade de participantes. Não reutilizar os exemplos DEMO como evidência de desempenho.

## Nasdaq NQ/MNQ + Treasury (experimental, 2026-10-18)
O WebSocket pode fornecer trades NQ/MNQ e um proxy de juros `ZN` (preço de futuro, tipicamente inverso ao rendimento) ou `US10Y` com campo `rate` em pontos percentuais. Exige dados com timestamps sincronizados (<=1,5 s), movimento de juros em 5s, amostra de agressão de 5s >=1,8x média direcional de 3min anteriores (mínimo 2 min de referência) e participação direcional >=65%. Compra: rendimento em queda + agressão compradora; venda: rendimento em alta + agressão vendedora. O sinal confirmado também exige rompimento, deslocamento e qualidade de dados. Sem Treasury fresco, bloqueia confluência e entradas. DEMO não inventa Treasury. Feed real, simbologia e parâmetros precisam de validação; não há ordens automáticas, livro completo ou evidência de rentabilidade. ZN não é uma taxa de rendimento e não oferece conversão direta para pontos-base sem modelagem. `ZN` e `US10Y` são identificadores de mensagens normalizadas de backend, não símbolos Massive garantidos.
