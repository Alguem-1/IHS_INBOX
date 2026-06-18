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


def _san_token(v) -> str:
    """Sanitiza um pedaço do nome da pasta (fatura/BL). Diferente de _safe_name:
    devolve "" quando vazio, pra a parte ser OMITIDA do nome (sem 'SEM NOME')."""
    s = "" if v is None else str(v).strip()
    s = re.sub(r'[\\/:*?"<>|]+', " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _folder_name(reference: str, fatura="", bl="") -> str:
    """Nome da pasta do processo: reference[_fatura][_bl], omitindo o que faltar.
    Ex.: 'IHS057-26_INV12345_MEDU98765', 'IHS057-26_INV12345', 'IHS057-26'."""
    ref = (reference or "").strip().upper()
    parts = [p for p in (ref, _san_token(fatura), _san_token(bl)) if p]
    return "_".join(parts) if parts else "SEM PROCESSO"


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

    # ── pastas de processo (nome enriquecido ref_fatura_bl) ───────
    @staticmethod
    def _find_existing_folder(importer_dir: Path, ref: str):
        """Acha a pasta que 'pertence' ao processo `ref` dentro do importador:
        nome == ref ou começa com ref + '_'. A reference é a chave estável."""
        ref = (ref or "").strip().upper()
        if not ref or not importer_dir.is_dir():
            return None
        for child in importer_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name.upper()
            if name == ref or name.startswith(ref + "_"):
                return child
        return None

    def _folder_name_from_cache(self, reference: str) -> str:
        """Monta o nome enriquecido lendo fatura/BL do cache do UTILS (se houver)."""
        ref = (reference or "").strip().upper()
        if not ref:
            return "SEM PROCESSO"
        row = self.db.get_cached_process(ref)
        if row is None:
            return ref
        return _folder_name(ref, row["invoice_number"], row["bl_number"])

    def process_dir(self, importer: str, reference: str, create=False) -> Path:
        """Caminho da pasta do processo dentro do importador. Reusa a pasta já
        existente (achada pela reference); senão usa o nome enriquecido do cache.
        Com create=True garante que a árvore exista."""
        importer = _safe_name(importer)
        ref = (reference or "").strip().upper()
        importer_dir = self.root / importer
        if ref:
            existing = self._find_existing_folder(importer_dir, ref)
            folder = existing if existing else importer_dir / self._folder_name_from_cache(ref)
        else:
            folder = importer_dir / "SEM PROCESSO"
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        return folder

    def sync_process_folders(self, processes, report=None, is_canceled=None) -> dict:
        """O botão. Para cada processo do UTILS, garante a pasta
        importador/REF[_fatura][_bl]: cria se faltar, RENOMEIA a pasta existente
        quando o nome enriquecido muda (e atualiza o rel_path dos documentos).
        Idempotente. Nunca aborta o lote — erros por processo são acumulados.

        `report(feitos, total, rótulo)` (opcional) emite progresso por processo;
        `is_canceled()` (opcional) permite parar entre processos com segurança —
        cada processo é tratado por inteiro (cria, ou renomeia+reparenta, ou nem
        começa), então cancelar deixa a biblioteca consistente."""
        result = {"created": [], "renamed": [], "skipped": 0,
                  "no_importer": 0, "errors": [], "canceled": False}
        total = len(processes)
        for i, p in enumerate(processes):
            if is_canceled and is_canceled():
                result["canceled"] = True
                break
            ref = (p["reference"] or "").strip().upper() if p["reference"] else ""
            if report:
                report(i, total, ref)
            if not ref:
                continue
            importer = (p["importer"] or "").strip() if p["importer"] else ""
            if not importer:
                result["no_importer"] += 1
                continue
            try:
                importer_dir = self.root / _safe_name(importer)
                importer_dir.mkdir(parents=True, exist_ok=True)
                desired = _folder_name(ref, p["invoice_number"], p["bl_number"])
                existing = self._find_existing_folder(importer_dir, ref)
                if existing is None:
                    target = importer_dir / desired
                    target.mkdir(parents=True, exist_ok=True)
                    self.db.log("mkdir_process", "", "", str(target),
                                f"{importer} / {ref}")
                    result["created"].append(self._rel(target))
                elif existing.name == desired:
                    result["skipped"] += 1
                else:
                    target = importer_dir / desired
                    if target.exists():
                        # colisão inesperada: não mexe, registra como erro leve.
                        result["errors"].append(
                            f"{ref}: já existe '{desired}' (não renomeei)")
                        continue
                    old_rel = self._rel(existing)
                    existing.rename(target)
                    new_rel = self._rel(target)
                    n = self.db.reparent_documents(old_rel, new_rel)
                    self.db.log("rename_process", "", str(existing), str(target),
                                f"{importer} / {ref} ({n} docs)")
                    result["renamed"].append((old_rel, new_rel))
            except Exception as e:  # nunca derruba o lote
                result["errors"].append(f"{ref}: {e}")
        return result

    # ── ingestão ──────────────────────────────────────────────────
    def commit(self, src_path: str, importer: str, process_ref: str,
               doc_type: str, sha256: str = None, subdir: str = "") -> IngestResult:
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

        # Move pra Importador/Processo/ (nome enriquecido ref_fatura_bl quando
        # o cache do UTILS tiver fatura/BL; reusa a pasta já existente do processo).
        folder = self.process_dir(importer, process_ref, create=True)
        # Preserva a subestrutura de pastas que veio junto (ex.: 'Docs finais/').
        if subdir:
            folder = folder.joinpath(*[_safe_name(part) for part in Path(subdir).parts])
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
