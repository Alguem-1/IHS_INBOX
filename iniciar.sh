#!/usr/bin/env bash
# iniciar.sh — Launcher auto-bootstrap do IHS_INBOX.
# 1ª execução: cria .venv e instala requirements.txt. Depois: só executa.
# Roda a partir da própria pasta (cwd = IHS_INBOX) para o IHS_HUB detectar
# "rodando" pelo cwd em /proc.
set -e
cd "$(dirname "$(readlink -f "$0")")"

if [ ! -d ".venv" ]; then
    echo "[IHS_INBOX] Primeira execução — criando ambiente virtual..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python main.py
