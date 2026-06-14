"""
db.py — Índice SQLite do IHS_INBOX. Fica em <raiz_da_biblioteca>/.ihs_inbox.db
para viajar junto com a biblioteca (os caminhos são RELATIVOS à raiz).

Guarda só METADADOS de organização — nunca conteúdo fiscal interpretado.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256        TEXT UNIQUE NOT NULL,
    rel_path      TEXT NOT NULL,
    original_name TEXT,
    doc_type      TEXT,
    process_ref   TEXT,
    importer      TEXT,
    size_bytes    INTEGER,
    status        TEXT DEFAULT 'recebido',
    received_at   TEXT,
    ocr_text      TEXT,
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_process  ON documents(process_ref);
CREATE INDEX IF NOT EXISTS idx_docs_importer ON documents(importer);
CREATE INDEX IF NOT EXISTS idx_docs_type     ON documents(doc_type);

CREATE TABLE IF NOT EXISTS processes_cache (
    reference      TEXT PRIMARY KEY,
    importer       TEXT,
    client_id      INTEGER,
    status         TEXT,
    invoice_number TEXT,
    bl_number      TEXT,
    di_number      TEXT,
    synced_at      TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT,
    action    TEXT,
    sha256    TEXT,
    from_path TEXT,
    to_path   TEXT,
    detail    TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    """Índice da biblioteca. Uma instância por raiz de biblioteca."""

    def __init__(self, library_root: str):
        self.library_root = Path(library_root)
        self.library_root.mkdir(parents=True, exist_ok=True)
        self.path = self.library_root / ".ihs_inbox.db"
        # check_same_thread=False: o acesso é serializado pela app (a UI espera
        # o worker terminar), então é seguro tocar o índice da thread de rede/hash.
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ── documents ─────────────────────────────────────────────────
    def find_by_hash(self, sha256: str):
        return self.conn.execute(
            "SELECT * FROM documents WHERE sha256 = ?", (sha256,)).fetchone()

    def add_document(self, *, sha256, rel_path, original_name, doc_type,
                     process_ref, importer, size_bytes, notes="") -> int:
        cur = self.conn.execute(
            """INSERT INTO documents
               (sha256, rel_path, original_name, doc_type, process_ref,
                importer, size_bytes, status, received_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sha256, rel_path, original_name, doc_type, process_ref,
             importer, size_bytes, "recebido", _now(), notes))
        self.conn.commit()
        return cur.lastrowid

    def remove_document(self, doc_id: int) -> None:
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()

    def get_document(self, doc_id: int):
        return self.conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()

    def set_status(self, doc_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))
        self.conn.commit()

    def search(self, text="", importer=None, process_ref=None, doc_type=None):
        sql = "SELECT * FROM documents WHERE 1=1"
        args: list = []
        if text:
            sql += (" AND (original_name LIKE ? OR process_ref LIKE ?"
                    " OR importer LIKE ? OR doc_type LIKE ?)")
            like = f"%{text}%"
            args += [like, like, like, like]
        if importer:
            sql += " AND importer = ?"; args.append(importer)
        if process_ref:
            sql += " AND process_ref = ?"; args.append(process_ref)
        if doc_type:
            sql += " AND doc_type = ?"; args.append(doc_type)
        sql += " ORDER BY importer, process_ref, doc_type, original_name"
        return self.conn.execute(sql, args).fetchall()

    def list_importers(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT importer FROM documents "
            "WHERE importer IS NOT NULL AND importer != '' ORDER BY importer"
        ).fetchall()
        return [r["importer"] for r in rows]

    def list_processes(self, importer=None) -> list[str]:
        if importer:
            rows = self.conn.execute(
                "SELECT DISTINCT process_ref FROM documents WHERE importer = ? "
                "AND process_ref IS NOT NULL AND process_ref != '' "
                "ORDER BY process_ref", (importer,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT DISTINCT process_ref FROM documents "
                "WHERE process_ref IS NOT NULL AND process_ref != '' "
                "ORDER BY process_ref").fetchall()
        return [r["process_ref"] for r in rows]

    # ── processes_cache (espelho só-leitura do UTILS) ─────────────
    def upsert_processes(self, processes: list[dict]) -> None:
        for p in processes:
            self.conn.execute(
                """INSERT INTO processes_cache
                   (reference, importer, client_id, status,
                    invoice_number, bl_number, di_number, synced_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(reference) DO UPDATE SET
                     importer=excluded.importer, client_id=excluded.client_id,
                     status=excluded.status, invoice_number=excluded.invoice_number,
                     bl_number=excluded.bl_number, di_number=excluded.di_number,
                     synced_at=excluded.synced_at""",
                (p.get("reference"), p.get("importer"), p.get("client_id"),
                 p.get("status"), p.get("invoice_number"), p.get("bl_number"),
                 p.get("di_number"), _now()))
        self.conn.commit()

    def get_cached_process(self, reference: str):
        return self.conn.execute(
            "SELECT * FROM processes_cache WHERE reference = ?",
            (reference,)).fetchone()

    def all_cached_processes(self) -> list:
        return self.conn.execute(
            "SELECT * FROM processes_cache ORDER BY importer, reference").fetchall()

    def cached_process_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM processes_cache").fetchone()["n"]

    def reparent_documents(self, old_prefix: str, new_prefix: str) -> int:
        """Reaponta os documentos quando a pasta de um processo é renomeada:
        troca o prefixo de rel_path de old_prefix/ para new_prefix/. Os prefixos
        são caminhos POSIX relativos à raiz (ex.: 'IMP/IHS057-26'). Retorna o
        número de linhas atualizadas.

        Casa o prefixo por comparação EXATA (substr), não com LIKE: o nome da
        pasta antiga pode conter '_' (ex.: 'REF_FATURA' → 'REF_FATURA_BL') e no
        LIKE o '_' é curinga, o que poderia atingir documentos de outro processo."""
        cut = len(old_prefix) + 1          # preserva a '/' que inicia o resto
        cur = self.conn.execute(
            "UPDATE documents SET rel_path = ? || substr(rel_path, ?) "
            "WHERE substr(rel_path, 1, ?) = ?",
            (new_prefix, cut, cut, old_prefix + "/"))
        self.conn.commit()
        return cur.rowcount

    # ── audit_log ─────────────────────────────────────────────────
    def log(self, action, sha256="", from_path="", to_path="", detail="") -> None:
        self.conn.execute(
            "INSERT INTO audit_log (ts, action, sha256, from_path, to_path, detail) "
            "VALUES (?,?,?,?,?,?)",
            (_now(), action, sha256, from_path, to_path, detail))
        self.conn.commit()

    def list_audit(self, limit=200):
        return self.conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
