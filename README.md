# IHS INBOX

Organizador e arquivo central dos **documentos recebidos** de importação
(invoice, packing list, BL, capa, fechamento, extratos…). Faz parte do
ecossistema IHS e nasce pra virar o **5º card do IHS_HUB**.

> **Princípio inegociável:** o INBOX **nunca interpreta conteúdo fiscal**. Ele
> guarda, organiza, acha e mostra o documento **original** pra você ler com os
> próprios olhos. Não transcreve valores, não preenche planilha, não decide
> nada que possa virar multa. OCR, quando usado, serve **só pra busca** — um
> erro de OCR vira no máximo uma busca que não casa, nunca um número errado.

## O que ele faz (resumo)

- Mantém uma **biblioteca nova** de documentos, organizada em
  **Importador → Processo → documentos**.
- Recebe arquivos de uma pasta-isca (downloads do PC, anexos de e-mail,
  arquivos de WhatsApp) e os **arquiva por triagem** — detectando o número do
  processo (`IHS057-26`) no nome e consultando o **IHS_UTILS** (só-leitura) pra
  descobrir o importador.
- **Não duplica** (dedup por hash) — economiza espaço.
- Busca, preview, checklist de documentos por processo, assistente de migração
  da biblioteca antiga e painel de espaço.

## Status

🌱 **Projeto novo / greenfield.** Ainda não há código — só o planejamento.
Leia o [`SPEC.md`](SPEC.md) (plano completo e fundamentado) antes de começar, e
o [`CLAUDE.md`](CLAUDE.md) (convenções e como se encaixa no ecossistema).
