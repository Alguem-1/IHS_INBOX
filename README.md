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

## Instalação no cliente (deploy via SSH + deploy key)

Cada cliente recebe uma **deploy key SSH só-leitura** do repositório no GitHub.
A instalação é sempre por **`git clone`** — nunca copiando a pasta:

```bash
git clone git@github.com:Alguem-1/IHS_INBOX.git
cd IHS_INBOX
./install_desktop.sh     # cria o atalho no menu
./iniciar.sh             # 1ª execução: monta o .venv e instala as dependências
```

> ⚠️ **Não copie a pasta do projeto entre máquinas.** A `.venv/` é local e tem
> caminhos absolutos da máquina de origem — copiada, ela vem **quebrada**. Ela
> está no `.gitignore` (não entra no git nem no GitHub) justamente por isso: o
> `iniciar.sh` recria um ambiente limpo no cliente. Sempre `git clone`.
>
> A deploy key é **SSH**, então o `origin` precisa ser `git@github.com:...`
> (e não a URL `https://`). Instale a chave como `~/.ssh/id_ed25519` ou via uma
> entrada `Host` no `~/.ssh/config`, pra que o `git pull` funcione mesmo quando
> o app é lançado pelo atalho do menu (sem terminal/ssh-agent).

## Atualização

Há um botão **"⟳ Atualizar app"** no canto superior direito (visível em todas as
abas). Ele roda `git pull --ff-only` no código — nunca faz merge, nunca empurra
e **nunca toca na biblioteca de documentos** (que vive fora do repo). Se houver
versão nova, oferece reiniciar o app pra aplicar. Veja [`updater.py`](updater.py).

## Status

🌱 **Projeto novo / greenfield.** Ainda não há código — só o planejamento.
Leia o [`SPEC.md`](SPEC.md) (plano completo e fundamentado) antes de começar, e
o [`CLAUDE.md`](CLAUDE.md) (convenções e como se encaixa no ecossistema).
