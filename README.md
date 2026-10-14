# Flow AI Terminal — MVP DEMO

Protótipo **100% simulado**, sem conexão com B3, Profit, OpenAI, Telegram ou corretora. Não gera sinais válidos para negociação.

## Teste local

Com Python instalado, execute na pasta do projeto:

```bash
python -m http.server 8000
```

Abra http://localhost:8000 no navegador. `file://` não suporta service workers.

## Publicação privada e iPhone

Não habilite GitHub Pages para este repositório privado sem entender a visibilidade da publicação: páginas publicadas podem ficar acessíveis publicamente em alguns planos. Para testar no iPhone, publique a demo em um serviço HTTPS autorizado; no Safari, use Compartilhar → Adicionar à Tela de Início.

## Limitações

- Lógica de demonstração não representa leitura de fluxo real, nem backtesting.
- Sem push, sem notificações e sem autenticação.
- `manifest.webmanifest` usa SVG; para compatibilidade iOS completa, produzir PNG 192/512 e ícone Apple Touch.
- Antes de dados reais: confirmar licença Nelogica/B3, fonte de dados, backend Windows e política de acesso.

## Próximos módulos

- `collector`: ProfitDLL Windows com tratamento de sequência, reconexão e contratos.
- `engine`: indicadores de fluxo auditáveis e testes históricos.
- `api`: feed WebSocket autenticado.
- `alerts`: Telegram ou Web Push com supressão de duplicados.
- `ai`: análise opcional de eventos estruturados (nunca por tick).
Versão demo 1.0
