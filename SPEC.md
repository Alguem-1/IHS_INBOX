# IHS INBOX — Especificação / Plano

Documento de planejamento para construir o **IHS_INBOX**. Escrito antes de
qualquer código. Tudo aqui foi discutido e **fundamentado no que já existe** nos
apps irmãos (especialmente o IHS_UTILS, cujo modelo de dados foi inspecionado).

---

## 1. Objetivo e princípio de segurança

O usuário é o ponta que **recebe** documentos de importação e alimenta os
sistemas. Os documentos chegam soltos (pasta, e-mail, WhatsApp), são **muitos**,
e a maior dor é **organizar e achar** o documento certo do processo certo.

O INBOX resolve isso **sem nunca assumir a responsabilidade do conteúdo**:

> **REGRA DE OURO:** o INBOX não lê, não transcreve e não interpreta nenhum
> valor fiscal (NCM, valores, pesos, quantidades). Ele guarda/organiza/acha/
> mostra o **arquivo original**. A leitura e a conferência continuam 100% com o
> ser humano. Isso é proposital: nesse domínio, um número errado gerado por
> software e confiado pelo operador pode virar multa altíssima. Então o app é
> de **organização**, não de extração.
>
> OCR pode existir, mas **apenas para indexar texto e permitir busca**. Um erro
> de OCR só causa uma busca que não encontra — nunca um dado autoritativo errado.

---

## 2. Onde se encaixa no ecossistema IHS

Todos os apps vivem em `/home/alguem/DEVPROJECTS/` e são lançados pelo
**IHS_HUB** (launcher PyQt6). Apps irmãos e o que já cobrem (para o INBOX **não
duplicar** nada):

| App | Papel | Já cobre |
|-----|-------|----------|
| **MOTHERBASE** | Task center | tarefas |
| **IHS_UTILS** | Gestão operacional/financeira (cliente/servidor + DB) | **Processos**, financeiro, contas a pagar, cross-reference, câmbio, prazos |
| **IHS_DUIMP** | Processa o espelho DUIMP | custo/DUIMP |
| **IHS_TOOLs** | Calculadoras comex | NCM, incoterms, impostos, conversões, custo |

O **buraco** que o INBOX preenche é a **entrada**: o que acontece com o
documento *quando ele chega na sua mão*, antes de virar processo nos outros
sistemas. Nenhum app hoje guarda/indexa/acha os PDFs recebidos.

Ideias que foram **descartadas** e por quê (não repetir):
- Extrair dados dos documentos (IHS_EXTRACT) → **risco de multa** se o operador
  confiar em valor extraído errado. Fora de escopo.
- Câmbio, prazos → já existem no IHS_UTILS.
- Custo → já existe no IHS_TOOLs e no IHS_DUIMP.
- Gerar documentos → o usuário **recebe** documentos, não gera.

---

## 3. Regras e decisões do usuário (vinculantes)

1. **Biblioteca nova.** No início o INBOX **não** toca na biblioteca atual (que
   é gerenciada manualmente). Ele cria uma biblioteca nova e o usuário vai
   **migrando os processos pra lá com calma**.
2. **Árvore por cliente.** A biblioteca é organizada por **importador →
   processo → documentos**. Não é uma pasta geral única; cada importador tem a
   sua pasta, e dentro dela os processos.
3. **Sem duplicados.** Há muitos documentos e espaço importa: **nada de
   guardar o mesmo arquivo duas vezes** (dedup por hash de conteúdo).
4. **Convenção de nº de processo:** `IHS057-26` → `IHS` + 3 dígitos + `-` + ano
   (2 dígitos). Regex: `IHS\d{3}-\d{2}` (case-insensitive recomendado).
5. **Integração com IHS_UTILS: só-leitura** no começo. Puxa a lista de
   processos pra agrupar/vincular; **não escreve nada** no banco do UTILS;
   funciona mesmo com o servidor do UTILS desligado.
6. Documentos chegam por: **pasta no PC**, **e-mail (anexos)** e **WhatsApp**.

---

## 4. Modelo da biblioteca

```
IHS-Biblioteca/                      (raiz configurável)
  GOGA DISTRIBUICAO/                 (importador, vindo do UTILS: Process.importer)
    IHS057-26/                       (processo, Process.reference)
      invoice/ packing/ BL/ capa/ fechamento/ extrato/ ...  (ou plano, com tipo na tag)
    IHS061-26/
  OUTRO IMPORTADOR/
    IHS058-26/
```

- Mover (não copiar) para a biblioteca por padrão — economiza espaço. (Copiar
  pode ser uma opção, mas o usuário priorizou não duplicar.)
- **Nunca apagar o original em silêncio.** Mover é reversível (lixeira/undo da
  última ação) e há **log de auditoria**.

---

## 5. Fluxo diário — "dropzone + triagem"

1. Uma (ou mais) **pasta-isca** configurável (ex.: `~/Downloads`, ou uma pasta
   "Entrada") onde caem os arquivos do PC, anexos de e-mail e downloads de
   WhatsApp. O INBOX **vigia** essas pastas.
2. Para cada arquivo novo, a **fila de triagem** mostra um palpite:
   - Lê `IHS\d{3}-\d{2}` do nome do arquivo.
   - Consulta o IHS_UTILS (só-leitura) → descobre **importador** e dados do
     processo.
   - Sugere **tipo de documento** por palavra-chave no nome (`capa`,
     `fechamento`, `extrato`, `invoice`, `packing`, `bl`, `di`…). Só etiqueta.
3. Usuário **confirma num clique** → arquivo vai pra `Importador/Processo/`.
   Arquivos não reconhecidos ficam na fila pra atribuição manual (incl. em
   lote: selecionar vários e atribuir o mesmo processo).
4. Antes de gravar: **dedup por hash**. Se o conteúdo idêntico já existe na
   biblioteca, avisa "já está em IHS057-26" e **não duplica** (resolve o mesmo
   doc chegando por e-mail *e* WhatsApp).

---

## 6. Funcionalidades

### MVP (1ª versão)
- Biblioteca **Importador → Processo** (raiz configurável).
- **Dropzone + triagem** com auto-detecção do `IHS057-26` e tipo por nome.
- **Dedup por hash (SHA-256)** — não armazena conteúdo repetido.
- **Busca** na biblioteca: por importador, processo, tipo, data, nome.
- **Preview** inline de PDF/imagem.
- **Índice próprio em SQLite** (o INBOX guarda o seu índice; ver §8).
- Integração **só-leitura** com o UTILS pra resolver importador do processo.
- **Undo da última ação** + log de auditoria.

### Fases seguintes
- **Assistente de migração**: aponta pra uma pasta velha → escaneia → propõe um
  plano (cliente/processo/tipo) → revisão → migra em lotes com dedup.
  Pré-visualização antes de mover, **nada destrutivo**.
- **Painel de espaço**: tamanho total, por cliente, maiores arquivos,
  **duplicados recuperáveis**.
- **Checklist por processo**: esperados × presentes ("IHS057-26 sem BL"),
  guiado pelos campos do UTILS (tem `invoice_number`? `bl_number`? `di_number`?)
  e/ou por um conjunto de tipos esperados por `status`.
- **Alerta "processo sem documentos"**: cruza processos ativos do UTILS com as
  pastas e mostra os que estão vazios/incompletos.
- **OCR para busca** (find-only) em PDFs escaneados/imagens.
- **Arrastar pra fora** (drag-out) — puxar um documento do INBOX direto pro
  e-mail/WhatsApp.
- **Ingestão de e-mail** (IMAP) e watcher de pasta do WhatsApp Desktop.
- **Normalização de nome** ao arquivar (mantendo o nome original no índice).

---

## 7. Integração com o IHS_UTILS (fundamentada)

O UTILS é **cliente/servidor** com **API HTTP** (`server/app.py`), banco SQLite
(`server/ihs_utils.db`) e um cliente REST pronto em
`client/api_client.py` (classe `ApiClient`).

**Modelo `Process`** (`IHS_UTILS/server/models.py`) — campos úteis ao INBOX:

```
reference        # nº do processo, ex.: "IHS057-26"   ← chave de vínculo
importer         # nome do importador                 ← define a pasta do cliente
client_id        # id do importador
exporter
invoice_number   # → checklist (espera invoice?)
bl_number        # → checklist (espera BL?)
di_number        # → checklist (espera DI?)
status           # "DOCUMENTATION", etc.
ncm_codes, eta, embarque, freetime, fim_freetime, data_desembaraco, notes
```

Há também uma classe `Importador` (cadastro de clientes).

**`ApiClient` (`client/api_client.py`)** — já oferece, entre outros:
`list_processes(...)`, `list_processes_for_table(...)`, `get_process(id)`,
`get_process_full(id)`. Autenticação por `server_url` + `token` (sessão
`requests` com header de auth). Construtor:
`ApiClient(server_url, token, username, is_admin_flag)`.

**Como o INBOX usa (só-leitura):**
- Reusar/espelhar o `ApiClient` (ou copiar o mínimo necessário) e chamar
  **apenas** os métodos de leitura (`list_processes`, `get_process*`).
- Mapear `reference` → `importer` pra **arquivar no cliente certo**
  automaticamente.
- Usar `invoice_number`/`bl_number`/`di_number`/`status` pro **checklist**.
- **Nunca** chamar `create/update/delete/patch`. Começar 100% read-only.
- **Tolerante a servidor offline:** se o UTILS não responder, o INBOX continua
  funcionando com o índice próprio; só perde o auto-preenchimento de importador
  (cai pra atribuição manual / cache local da última lista de processos).
- Config de `server_url`/`token`: provavelmente dá pra **reaproveitar a config
  do cliente do UTILS** (ver `client/config_manager.py`) — investigar pra não
  pedir login duas vezes.

> Caminhos de referência (somente para leitura/estudo, não modificar):
> `/home/alguem/DEVPROJECTS/IHS_UTILS/client/api_client.py`
> `/home/alguem/DEVPROJECTS/IHS_UTILS/server/models.py`
> `/home/alguem/DEVPROJECTS/IHS_UTILS/client/config_manager.py`

---

## 8. Índice próprio (SQLite) — esboço

O INBOX mantém **o próprio banco** (desacoplado do UTILS). Tabela central
sugerida:

```sql
CREATE TABLE documents (
    id           INTEGER PRIMARY KEY,
    sha256       TEXT UNIQUE NOT NULL,   -- dedup: conteúdo único
    path         TEXT NOT NULL,          -- caminho atual na biblioteca
    original_name TEXT,                  -- nome de origem (auditoria)
    doc_type     TEXT,                   -- invoice/packing/bl/capa/... (tag)
    process_ref  TEXT,                   -- "IHS057-26"
    importer     TEXT,                   -- nome do cliente (da pasta)
    status       TEXT,                   -- recebido/conferido (setado por humano)
    ocr_text     TEXT,                   -- só pra busca (fase 2)
    received_at  TEXT,
    notes        TEXT
);
```

- **Dedup** = `sha256` UNIQUE. Ao ingerir, calcula o hash; se já existe, avisa e
  não grava cópia.
- Opcional: cache da lista de processos do UTILS pra funcionar offline.

---

## 9. Convenções técnicas (espelhar os apps irmãos)

Manter consistência com IHS_HUB / IHS_TOOLs / IHS_DUIMP:

- **PyQt6**, tema **dark** (copiar o estilo de `theme.py` dos irmãos —
  fundo `#050505`). Considerar reaproveitar os acentos "MGS/codec" do IHS_HUB se
  quiser, mas o dark base é o padrão da suite.
- **`iniciar.sh`** — launcher auto-bootstrap: `cd` pra própria pasta via
  `readlink -f`, cria `.venv` e `pip install -r requirements.txt` na 1ª vez,
  depois `exec .venv/bin/python main.py`.
- **`install_desktop.sh`** — escreve `~/.local/share/applications/ihs-inbox.desktop`
  e copia `logo.png` pro tema XDG como `ihs-inbox.png`. `.desktop` usa
  `Icon=ihs-inbox` e `StartupWMClass=ihs-inbox`, que deve casar com
  `app.setDesktopFileName("ihs-inbox")` no `main.py`.
- **`requirements.txt`** — PyQt6 (+ `requests` pra falar com a API do UTILS;
  `PyMuPDF`/`pdf2image`+`pytesseract` só na fase de OCR).
- Textos e comentários em **português (pt-BR)**.
- Sem segredo no repo; `.gitignore` com `.venv/`, `__pycache__/`, `*.pyc`,
  e a **biblioteca de documentos NÃO entra no git** (dados sensíveis + tamanho).

### Estrutura de arquivos sugerida
```
IHS_INBOX/
  main.py            # janela principal (abas/painéis)
  theme.py           # paleta dark (copiar dos irmãos)
  db.py              # índice SQLite
  library.py         # mover/organizar/dedup/árvore cliente→processo
  intake.py          # watcher das pastas-isca + fila de triagem
  utils_api.py       # cliente só-leitura da API do IHS_UTILS
  iniciar.sh
  install_desktop.sh
  requirements.txt
  logo.png
```

---

## 10. Virar o 5º card do IHS_HUB

Quando o `iniciar.sh` estiver de pé, adicionar **uma entrada** na lista
`PROJECTS` em `/home/alguem/DEVPROJECTS/IHS_HUB/main.py`:

```python
{
    "title": "IHS INBOX",
    "subtitle": "Arquivo de documentos de importação",
    "exec": _p("IHS_INBOX", "iniciar.sh"),
    "logo": _p("IHS_INBOX", "logo.png"),
    "freq": "143.40",   # frequência codec (sabor MGS do hub)
},
```

O hub detecta "rodando" pelo `cwd` do processo (varre `/proc`), então nada mais
precisa ser configurado. (O hub é grade 2×N; 5 cards já acomodam.)

---

## 11. Decisões em aberto (resolver com o usuário ao construir)

- Mover vs copiar para a biblioteca (default: **mover**, pra não duplicar).
- Onde fica a raiz da biblioteca (perguntar no 1º uso).
- Layout dos documentos dentro do processo: subpastas por tipo **ou** plano com
  tag de tipo (sugestão: **plano + tag**, mais simples de buscar).
- Reaproveitar a config/login do cliente do UTILS ou ter config própria.
- Tipos de documento canônicos (lista fechada): invoice, packing list, BL,
  capa, fechamento, extrato, DI/DUIMP, CI, outros.
- Nome do `.desktop`/ícone: `ihs-inbox` (sugerido).

---

## 12. Resumo de uma linha

Um **gerenciador de biblioteca de documentos recebidos**, organizado por
**cliente → processo**, com **triagem automática** pelo nº `IHS057-26` (resolvido
via UTILS só-leitura), **dedup** pra economizar espaço, e **busca/preview/
checklist** — que **nunca interpreta conteúdo fiscal**, só organiza e mostra o
original.
