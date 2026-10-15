# Flow AI Terminal Gold — módulo experimental

## Instalação no repositório
Adicione `gold.html` e `gold.js` na raiz de `caskesties/Flow-ai-terminal` usando **Add file → Upload files** no GitHub. Após o GitHub Pages publicar, abra `https://caskesties.github.io/Flow-ai-terminal/gold.html` (se o Pages usar esse endereço padrão). O app original (`index.html`) não é modificado.

## Recursos
- Demo sintética; reprodução local de CSV de trades; assinatura WebSocket segura `wss://` a partir de **servidor próprio**.
- Contratos GC e MGC; delta agressor, volume, imbalance, negócios/segundo, deslocamento e score heurístico ilustrativo.
- Alertas locais e exportação CSV, sem execução de ordens.

## Esquema de mensagem do servidor
Uma mensagem JSON por negócio (ou array de objetos):
`{"type":"trade","timestamp":"2026-10-15T18:00:00.000Z","symbol":"GC","price":2650.1,"size":5,"side":"buy"}`

`side` deve ser classificação **real e confiável** do agressor e não uma suposição baseada no preço. Campos de livro de ofertas, sequenciamento e snapshots não estão implementados.
O cliente emite ao conectar: `{"type":"subscribe","symbol":"GC"}` (ou `MGC`).

**Nunca** inserir credenciais de fornecedor em JavaScript exposto ou no GitHub Pages. Execute bridge em backend com TLS, controle de acesso, validação de origem, rate limiting e verificação de direitos de redistribuição/exibição da CME e do fornecedor. O WebSocket é somente um ponto de integração, não um conector específico de Databento/NinjaTrader.

## Limitações importantes
- CSV é reprodução acelerada, não backtest temporal fiel; métricas refletem os últimos 60 s **de timestamps do arquivo**.
- Score é heurístico sem calibração; não identifica bancos, ordens iceberg, spoofing ou absorção comprovada.
- Alertas não validam eficiência, lucratividade, slippage ou latência.
- Browser em segundo plano no iPhone pode suspender WebSocket; produção exige serviço de ingestão persistente e tratamento de reconexão/ordenação/deduplicação.
