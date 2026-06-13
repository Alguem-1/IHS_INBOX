# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado atual

🌱 **Greenfield.** Ainda não há código — apenas o planejamento. **Leia o
[`SPEC.md`](SPEC.md) por inteiro antes de começar** (é o plano fundamentado,
com as regras do usuário e a integração já investigada com o IHS_UTILS).

## O que é

IHS_INBOX é um **organizador de documentos recebidos** de importação (invoice,
packing list, BL, capa, fechamento, extratos…), no ecossistema IHS. Vai virar o
5º card do **IHS_HUB**. Organiza uma biblioteca nova por **importador →
processo (`IHS057-26`) → documentos**, com triagem automática, dedup por hash,
busca e preview.

## Regra de ouro (não viole)

O INBOX **NUNCA interpreta conteúdo fiscal** (valores, NCM, pesos,
quantidades). Ele guarda/organiza/acha/mostra o **documento original** pra o
humano ler. Não transcreve, não preenche planilha, não gera dado autoritativo —
porque um número errado confiado pelo operador pode virar **multa**. OCR (fase
futura) serve **só pra busca**, nunca pra preencher campos.

## Integração com o IHS_UTILS — **só-leitura**

O UTILS tem API HTTP + `ApiClient` em
`/home/alguem/DEVPROJECTS/IHS_UTILS/client/api_client.py` e o modelo `Process`
em `.../server/models.py` (campos `reference`, `importer`, `client_id`,
`invoice_number`, `bl_number`, `di_number`, `status`…). Use **apenas** os
métodos de leitura (`list_processes`, `get_process*`) pra mapear processo →
importador e montar checklist. **Nunca** chamar create/update/delete/patch. O
INBOX deve funcionar mesmo com o servidor do UTILS desligado (índice próprio em
SQLite + cache). Esses caminhos do UTILS são **referência só pra leitura — não
modificar outro projeto**.

## Convenções (espelhar IHS_HUB / IHS_TOOLs / IHS_DUIMP)

- **PyQt6**, tema dark (`#050505`); copiar o estilo de `theme.py` dos irmãos.
- **`iniciar.sh`** auto-bootstrap (`.venv` + `requirements.txt` na 1ª vez, depois
  `exec .venv/bin/python main.py`).
- **`install_desktop.sh`** com `Icon=ihs-inbox` / `StartupWMClass=ihs-inbox`
  casando com `app.setDesktopFileName("ihs-inbox")`.
- Textos e comentários em **português (pt-BR)**.
- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`. **A biblioteca de documentos
  nunca entra no git** (sensível + tamanho).

## Convidando para o hub

Quando rodar, adicionar 1 entrada na lista `PROJECTS` em
`/home/alguem/DEVPROJECTS/IHS_HUB/main.py` (`title/subtitle/exec/logo/freq`) —
ver §10 do `SPEC.md`. O hub detecta "rodando" pelo `cwd` em `/proc`, então não
precisa de mais nada.
