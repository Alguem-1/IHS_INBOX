"""
updater.py — Auto-atualização do código via `git pull` (deploy key só-leitura).

O IHS_INBOX é distribuído nos clientes como um clone git do repositório; cada
cliente recebe uma deploy key SSH (só-leitura). O botão "Atualizar app" puxa a
versão mais recente com `git pull --ff-only` — NUNCA empurra, NUNCA faz merge e
NUNCA toca na biblioteca de documentos (que mora fora do repo, em
~/IHS-Biblioteca). Só atualiza o código-fonte do próprio app.
"""

import os
import subprocess
from pathlib import Path

# Diretório do repositório = onde mora o código do INBOX (este arquivo).
REPO_DIR = Path(__file__).resolve().parent

# Tempo máximo de espera por um comando git (rede pode estar lenta/offline).
_TIMEOUT = 120


class UpdateResult:
    """Resultado de uma tentativa de atualização, pronto p/ a UI interpretar."""

    def __init__(self, status, message, old=None, new=None, files=0, detail=""):
        # status: "uptodate" | "updated" | "notgit" | "error"
        self.status = status
        self.message = message      # frase amigável p/ mostrar ao usuário
        self.old = old              # revisão antes do pull (hash curto)
        self.new = new              # revisão depois do pull (hash curto)
        self.files = files          # nº de arquivos alterados (se "updated")
        self.detail = detail        # saída crua do git (p/ diagnóstico)

    @property
    def changed(self) -> bool:
        return self.status == "updated"


def _git(*args, cwd=REPO_DIR, timeout=_TIMEOUT):
    """Roda um comando git e devolve (returncode, saída combinada). Nunca levanta:
    timeout ou git ausente viram returncode != 0 com uma mensagem."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            # Evita que o git abra editor/pager ou peça senha interativa e trave a
            # thread; sem terminal, uma falha de auth vira erro em vez de prompt.
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"},
        )
    except subprocess.TimeoutExpired:
        return 124, "git demorou demais (timeout)"
    except OSError as e:
        return 127, f"não foi possível executar o git: {e}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def current_revision(cwd=REPO_DIR) -> str:
    """Hash curto da revisão atual (ou '?' se não for um repo git)."""
    rc, out = _git("rev-parse", "--short", "HEAD", cwd=cwd)
    return out if rc == 0 else "?"


def _friendly_error(out: str) -> str:
    """Traduz erros comuns do git para uma frase compreensível ao cliente."""
    low = out.lower()
    if "permission denied" in low or "publickey" in low:
        return ("Sem permissão para acessar o repositório. A deploy key SSH "
                "deste computador não está configurada ou foi revogada.")
    if "could not resolve host" in low or "could not read from remote" in low \
            or "network is unreachable" in low or "timed out" in low:
        return ("Sem conexão com o repositório. Verifique a internet e tente "
                "de novo.")
    if "local changes" in low or "would be overwritten" in low or "stash" in low:
        return ("Há alterações locais no código que impedem a atualização. "
                "Esta cópia foi modificada manualmente.")
    if "not possible to fast-forward" in low or "diverging" in low \
            or "have diverged" in low:
        return ("Esta cópia divergiu do repositório (tem commits locais) e não "
                "pode ser atualizada por fast-forward.")
    # Erro desconhecido: mostra a saída crua do git, enxuta.
    return out or "Falha desconhecida ao atualizar."


def pull_updates() -> UpdateResult:
    """Puxa a versão mais recente. Pensado p/ rodar numa thread (sem UI)."""
    # 1) É mesmo um repositório git?
    rc, _ = _git("rev-parse", "--is-inside-work-tree")
    if rc != 0:
        return UpdateResult(
            "notgit",
            "Esta cópia não é um repositório git, então não dá para atualizar "
            "por aqui. Reinstale clonando o repositório com a deploy key.",
        )

    # 2) Guarda a revisão atual p/ comparar depois.
    rc_old, old_full = _git("rev-parse", "HEAD")
    old = old_full[:7] if rc_old == 0 else None

    # 3) Só fast-forward: nunca cria merge, nunca empurra, falha limpo se divergiu.
    rc, out = _git("pull", "--ff-only")
    if rc != 0:
        return UpdateResult("error", _friendly_error(out), old=old, detail=out)

    rc_new, new_full = _git("rev-parse", "HEAD")
    new = new_full[:7] if rc_new == 0 else None

    if old and new and old == new:
        return UpdateResult("uptodate", "Você já está na versão mais recente.",
                            old=old, new=new, detail=out)

    # 4) Conta quantos arquivos mudaram entre as duas revisões (informativo).
    n = 0
    if old_full and new_full:
        rc_d, diff = _git("diff", "--name-only", f"{old_full}..{new_full}")
        if rc_d == 0:
            n = len([ln for ln in diff.splitlines() if ln.strip()])

    return UpdateResult("updated", "Atualizado para a versão mais recente.",
                        old=old, new=new, files=n, detail=out)


class UpdateCheck:
    """Resultado da verificação de versão nova no arranque (só leitura)."""

    def __init__(self, available=False, behind=0, log="", error=""):
        self.available = available   # há commits novos p/ puxar?
        self.behind = behind         # quantos commits atrás do remoto
        self.log = log               # mini-changelog (git log --oneline)
        self.error = error           # diagnóstico interno (não mostrado ao cliente)


def check_for_updates(fetch_timeout=8, cwd=REPO_DIR) -> UpdateCheck:
    """Verifica, com `git fetch`, se o remoto tem commits novos. Falha SILENCIOSA:
    offline, sem deploy key, git ausente ou não-repo → available=False (o app abre
    normalmente). Não mexe na árvore de trabalho — só atualiza os refs do remoto."""
    rc, _ = _git("rev-parse", "--is-inside-work-tree", cwd=cwd)
    if rc != 0:
        return UpdateCheck(error="não é um repositório git")

    rc, out = _git("fetch", "--quiet", cwd=cwd, timeout=fetch_timeout)
    if rc != 0:
        return UpdateCheck(error=out)   # offline/auth/timeout: sem update conhecido

    # upstream da branch atual (ex.: origin/main); cai p/ origin/main se não houver
    rc, upstream = _git("rev-parse", "--abbrev-ref",
                        "--symbolic-full-name", "@{u}", cwd=cwd)
    if rc != 0 or not upstream:
        upstream = "origin/main"

    rc, count = _git("rev-list", "--count", f"HEAD..{upstream}", cwd=cwd)
    behind = int(count) if rc == 0 and count.isdigit() else 0
    if behind <= 0:
        return UpdateCheck(available=False, behind=0)

    rc, log = _git("log", "--oneline", "--no-decorate", f"HEAD..{upstream}", cwd=cwd)
    return UpdateCheck(available=True, behind=behind, log=log if rc == 0 else "")
