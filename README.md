# Flow AI Terminal v2 — DEMO

Protótipo 100% sintético para o WIN, sem conexão com B3, Nelogica, OpenAI, corretoras ou ordens de negociação.

## Funcionalidades
- Quatro cenários sintéticos reproduzíveis: pressão compradora, vendedora, absorção e lateralidade.
- Janela de até 75 eventos artificiais; delta, volume, velocidade, deslocamento, score experimental.
- Estados: observação, antecipado, confirmado e invalidado.
- Histórico local com exportação CSV.
- PWA com cache versionado, atualização online e abertura pelo ícone do iPhone.

## Atualizar GitHub Pages
Substitua `index.html`, `app.js`, `sw.js`, `README.md` na raiz do repositório existente. Conserve a pasta `.github/workflows/static.yml`. Commit na branch `main`. Aguarde GitHub Actions verde, feche e reabra o app. Pode ser necessário atualizar a página no Safari para renovar o cache.

## Aviso
Nenhum sinal é válido para negociação. O motor usa cenários inventados e regras não calibradas. Para produção: contrato/licença de dados, coleta confiável, teste fora da amostra, custos, slippage, latência, controles operacionais e revisão de segurança.
