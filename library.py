"""
library.py — Operações de arquivo da biblioteca: árvore importador→processo,
hash SHA-256, mover (não copiar), dedup, quarentena de duplicados, auditoria e
undo. Nunca apaga o original em silêncio — mover é reversível.
"""

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_CHUNK = 1024 * 1024  # 1 MiB

QUARANTINE = "_duplicados"   # pasta reservada (não é importador)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    """Sanitiza um nome de pasta (sem separadores, sem espaços nas pontas)."""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "SEM NOME"


def safe_move(src, dest, expected_sha: str) -> bool:
    """Move SEGURO: copia → confere o hash do destino → só então apaga a origem.
    Se a cópia não bater, apaga o destino e levanta erro (a origem fica INTACTA).
    Retorna True se a origem foi removida; False se o destino ficou OK mas não deu
    pra apagar a origem (o documento já está salvo na biblioteca, sem perda)."""
    src, dest = Path(src), Path(dest)
    try:
        shutil.copy2(str(src), str(dest))   # copia conteúdo + metadados
    except Exception:
        if dest.exists():                   # limpa cópia parcial; origem intacta
            try:
                dest.unlink()
            except OSError:
                pass
        raise
    if sha256_of(str(dest)) != expected_sha:   # conferência de integridade
        try:
            dest.unlink()
        except OSError:
            pass
        raise RuntimeError(f"Cópia não confere (hash diferente): {src.name}")
    try:
        src.unlink()                        # só agora apaga a origem
        return True
    except OSError:
        return False


@dataclass
class IngestResult:
    status: str            # "ingested" | "duplicate"
    sha256: str
    original_path: str
    original_name: str
    importer: str
    process_ref: str
    doc_type: str
    final_path: str = ""   # destino final (ingested) ou na quarentena (duplicate)
    doc_id: int = 0        # id no índice (ingested)
    dup_importer: str = "" # onde já estava (duplicate)
    dup_process: str = ""


class Library:
    def __init__(self, db, library_root: str):
        self.db = db
        self.root = Path(library_root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── helpers ───────────────────────────────────────────────────
    def abs_path(self, rel_path: str) -> Path:
        return self.root / rel_path

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    @staticmethod
    def _unique_dest(folder: Path, name: str) -> Path:
        """Evita sobrescrever: se já existe um arquivo com esse nome (conteúdo
        diferente, pois o dedup é por hash), gera 'nome (2).ext', etc."""
        dest = folder / name
        if not dest.exists():
            return dest
        stem, suffix = Path(name).stem, Path(name).suffix
        i = 2
        while True:
            cand = folder / f"{stem} ({i}){suffix}"
            if not cand.exists():
                return cand
            i += 1

    # ── ingestão ──────────────────────────────────────────────────
    def commit(self, src_path: str, importer: str, process_ref: str,
               doc_type: str, sha256: str = None) -> IngestResult:
        src = Path(src_path)
        original_name = src.name
        if sha256 is None:
            sha256 = sha256_of(src_path)

        importer = _safe_name(importer)
        process_ref = (process_ref or "").strip().upper()

        res = IngestResult(
            status="", sha256=sha256, original_path=str(src),
            original_name=original_name, importer=importer,
            process_ref=process_ref, doc_type=doc_type or "")

        # Dedup por conteúdo: se já existe, manda pra quarentena (nunca apaga).
        existing = self.db.find_by_hash(sha256)
        if existing:
            qdir = self.root / QUARANTINE / date.today().isoformat()
            qdir.mkdir(parents=True, exist_ok=True)
            dest = self._unique_dest(qdir, original_name)
            safe_move(src, dest, sha256)
            res.status = "duplicate"
            res.final_path = str(dest)
            res.dup_importer = existing["importer"] or ""
            res.dup_process = existing["process_ref"] or ""
            self.db.log("quarantine", sha256, str(src), str(dest),
                        f"duplicado de {existing['process_ref'] or '?'}")
            return res

        # Move pra Importador/Processo/
        folder = self.root / importer / (process_ref or "SEM PROCESSO")
        folder.mkdir(parents=True, exist_ok=True)
        dest = self._unique_dest(folder, original_name)
        size = src.stat().st_size
        safe_move(src, dest, sha256)
        rel = self._rel(dest)
        doc_id = self.db.add_document(
            sha256=sha256, rel_path=rel, original_name=original_name,
            doc_type=doc_type or "", process_ref=process_ref,
            importer=importer, size_bytes=size)
        self.db.log("ingest", sha256, str(src), str(dest),
                    f"{importer} / {process_ref} / {doc_type}")
        res.status = "ingested"
        res.final_path = str(dest)
        res.doc_id = doc_id
        return res

    # ── undo ──────────────────────────────────────────────────────
    def undo(self, res: IngestResult) -> bool:
        """Reverte um commit (ingested ou duplicate): devolve o arquivo à origem
        e remove a linha do índice (se houver)."""
        cur = Path(res.final_path)
        if not cur.exists():
            return False
        orig = Path(res.original_path)
        orig.parent.mkdir(parents=True, exist_ok=True)
        dest = orig if not orig.exists() else self._unique_dest(orig.parent, orig.name)
        safe_move(cur, dest, res.sha256)
        if res.status == "ingested" and res.doc_id:
            self.db.remove_document(res.doc_id)
        self.db.log("undo", res.sha256, str(cur), str(dest), f"desfez {res.status}")
        return True
