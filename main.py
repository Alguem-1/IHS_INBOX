"""
main.py — IHS_INBOX: organizador de documentos recebidos de importação.
Abas: Triagem (arquivar) · Biblioteca (busca/preview) · Auditoria.

Regra de ouro: o INBOX NUNCA interpreta conteúdo fiscal (valores, NCM, pesos,
quantidades). Só guarda / organiza / acha / mostra o arquivo original.
"""

import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QImage, QIcon, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QDialog, QSplitter, QScrollArea,
    QAbstractItemView, QPlainTextEdit,
)

import config
import theme as T
from db import DB
from library import Library, QUARANTINE
from intake import build_proposal, ProcessMatcher, DOC_TYPES, DOC_TYPE_LABELS
from worker import Worker
import utils_api

try:
    import fitz  # PyMuPDF — preview de PDF
except Exception:
    fitz = None


# ── helpers ───────────────────────────────────────────────────────
def human_size(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def render_preview(path: str, zoom: float = 2.0):
    """Renderiza a 1ª página (PDF via PyMuPDF) ou a imagem. None se não dá."""
    ext = Path(path).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"):
        pix = QPixmap(path)
        return pix if not pix.isNull() else None
    if ext == ".pdf" and fitz is not None:
        try:
            doc = fitz.open(path)
            if doc.page_count == 0:
                return None
            p = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = QImage(p.samples, p.width, p.height, p.stride,
                         QImage.Format.Format_RGB888)
            return QPixmap.fromImage(img.copy())
        except Exception:
            return None
    return None


def open_path(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


# ── diálogo de triagem ────────────────────────────────────────────
class TriageDialog(QDialog):
    COLS = ["Arquivo", "Processo", "Importador", "Tipo"]

    def __init__(self, proposals, known_importers, resolver, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Triagem — confirmar arquivamento")
        self.resize(840, 480)
        self.setStyleSheet(T.MAIN_STYLESHEET)
        self.proposals = proposals
        self.resolver = resolver
        self.known_importers = known_importers
        self.result_rows = []
        self._build()
        self._fill()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        title = QLabel(f"{len(self.proposals)} arquivo(s) para arquivar")
        title.setStyleSheet(T.LBL_PAGE_TITLE)
        lay.addWidget(title)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Processo p/ todos:"))
        self.inp_all = QLineEdit()
        self.inp_all.setPlaceholderText("IHS057-26")
        self.inp_all.setMaximumWidth(160)
        bar.addWidget(self.inp_all)
        btn_apply = QPushButton("Aplicar a todos")
        btn_apply.clicked.connect(self._apply_all)
        bar.addWidget(btn_apply)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)

        note = QLabel("O INBOX só organiza o arquivo original — não lê valores, "
                      "NCM, pesos nem quantidades.")
        note.setStyleSheet(T.LBL_HINT)
        note.setWordWrap(True)
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Arquivar")
        btn_ok.setStyleSheet(T.BTN_PRIMARY)
        btn_ok.clicked.connect(self._accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        lay.addLayout(row)

    def _fill(self):
        self.table.setRowCount(len(self.proposals))
        for i, p in enumerate(self.proposals):
            it = QTableWidgetItem(p.original_name)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it.setToolTip(p.path)
            self.table.setItem(i, 0, it)

            ed_proc = QLineEdit(p.process_ref)
            ed_proc.editingFinished.connect(lambda r=i: self._reresolve(r))
            if p.matched_by in ("fatura", "bl"):
                label = "fatura" if p.matched_by == "fatura" else "BL"
                hint = f"Processo deduzido pela {label}: {p.matched_via}"
                ed_proc.setToolTip(hint)
                ed_proc.setStyleSheet(f"border: 1px solid {T.ACCENT};")
                it.setToolTip(f"{p.path}\n({hint})")
            self.table.setCellWidget(i, 1, ed_proc)

            cb_imp = QComboBox()
            cb_imp.setEditable(True)
            cb_imp.addItems(self.known_importers)
            cb_imp.setCurrentText(p.importer)
            self.table.setCellWidget(i, 2, cb_imp)

            cb_type = QComboBox()
            for t in DOC_TYPES:
                cb_type.addItem(DOC_TYPE_LABELS.get(t, t), t)
            dt = p.doc_type if p.doc_type in DOC_TYPES else "OUTRO"
            cb_type.setCurrentIndex(DOC_TYPES.index(dt))
            self.table.setCellWidget(i, 3, cb_type)

    def _apply_all(self):
        ref = self.inp_all.text().strip().upper()
        if not ref:
            return
        imp = self.resolver(ref) if self.resolver else None
        for i in range(self.table.rowCount()):
            self.table.cellWidget(i, 1).setText(ref)
            if imp:
                self.table.cellWidget(i, 2).setCurrentText(imp)

    def _reresolve(self, r):
        ref = self.table.cellWidget(r, 1).text().strip().upper()
        cb_imp = self.table.cellWidget(r, 2)
        if ref and self.resolver and not cb_imp.currentText().strip():
            imp = self.resolver(ref)
            if imp:
                cb_imp.setCurrentText(imp)

    def _accept(self):
        self.result_rows = []
        for i, p in enumerate(self.proposals):
            ref = self.table.cellWidget(i, 1).text().strip().upper()
            imp = self.table.cellWidget(i, 2).currentText().strip()
            dtype = self.table.cellWidget(i, 3).currentData()
            self.result_rows.append((p.path, ref, imp, dtype))
        self.accept()


# ── diálogo: escolher subpastas ao arquivar uma pasta-mãe ──────────
class FolderPickDialog(QDialog):
    """Ao arquivar uma pasta-mãe com subpastas, escolher quais entram. Mostra o
    processo detectado pelo NOME da subpasta, pra ignorar as que não são de
    processo (e os arquivos dentro delas). Tudo marcado por padrão."""
    COLS = ["Arquivar?", "Pasta", "Processo detectado", "Arquivos"]

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arquivar pasta — escolher subpastas")
        self.resize(720, 480)
        self.setStyleSheet(T.MAIN_STYLESHEET)
        self.entries = entries
        self.selected_indices = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        title = QLabel(f"{len(self.entries)} item(ns) na pasta")
        title.setStyleSheet(T.LBL_PAGE_TITLE)
        lay.addWidget(title)
        note = QLabel("Desmarque as subpastas que NÃO são de processo — elas e os "
                      "arquivos dentro serão ignorados (nada é movido).")
        note.setStyleSheet(T.LBL_HINT)
        note.setWordWrap(True)
        lay.addWidget(note)

        self.table = QTableWidget(len(self.entries), len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for i, e in enumerate(self.entries):
            chk = QTableWidgetItem()
            chk.setFlags((chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                         & ~Qt.ItemFlag.ItemIsEditable)
            chk.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(i, 0, chk)
            icon = "🗎  " if e["loose"] else "📁  "
            self.table.setItem(i, 1, QTableWidgetItem(icon + e["name"]))
            self.table.setItem(i, 2, QTableWidgetItem(e["process"] or "— sem processo —"))
            self.table.setItem(i, 3, QTableWidgetItem(f'{e["count"]} arq.'))
        lay.addWidget(self.table, 1)

        tools = QHBoxLayout()
        b_all = QPushButton("Marcar todos")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none = QPushButton("Desmarcar todos")
        b_none.clicked.connect(lambda: self._set_all(False))
        b_noproc = QPushButton("Desmarcar sem processo")
        b_noproc.clicked.connect(self._uncheck_no_process)
        tools.addWidget(b_all)
        tools.addWidget(b_none)
        tools.addWidget(b_noproc)
        tools.addStretch(1)
        lay.addLayout(tools)

        row = QHBoxLayout()
        row.addStretch(1)
        b_cancel = QPushButton("Cancelar")
        b_cancel.clicked.connect(self.reject)
        b_ok = QPushButton("Continuar")
        b_ok.setStyleSheet(T.BTN_PRIMARY)
        b_ok.clicked.connect(self._accept)
        row.addWidget(b_cancel)
        row.addWidget(b_ok)
        lay.addLayout(row)

    def _set_all(self, on):
        st = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(st)

    def _uncheck_no_process(self):
        for i, e in enumerate(self.entries):
            if not e["process"]:
                self.table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)

    def _accept(self):
        self.selected_indices = [
            i for i in range(self.table.rowCount())
            if self.table.item(i, 0).checkState() == Qt.CheckState.Checked]
        self.accept()


# ── janela principal ──────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, library_root):
        super().__init__()
        self.setWindowTitle("IHS INBOX — Documentos de importação")
        self.resize(1120, 740)
        self.library_root = library_root
        self.db = DB(library_root)
        self.lib = Library(self.db, library_root)
        self.utils_client = None
        self.last_results = []   # IngestResult da última leva (p/ undo)
        self._workers = []

        self._build_ui()
        self._refresh_status()
        self._prompt_utils_login()   # login opcional + sync no arranque

    # ---- construção da UI ----
    def _build_ui(self):
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_triage_tab(), "Triagem")
        self.tabs.addTab(self._build_library_tab(), "Biblioteca")
        self.tabs.addTab(self._build_audit_tab(), "Auditoria")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

    def _build_triage_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        title = QLabel("Triagem de documentos")
        title.setStyleSheet(T.LBL_PAGE_TITLE)
        lay.addWidget(title)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(T.LBL_MUTED)
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        row = QHBoxLayout()
        b1 = QPushButton("Arquivar arquivo(s)…")
        b1.setStyleSheet(T.BTN_PRIMARY)
        b1.clicked.connect(self._archive_files)
        b2 = QPushButton("Arquivar pasta…")
        b2.clicked.connect(self._archive_folder)
        self.btn_undo = QPushButton("Desfazer último")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self._undo_last)
        b_folders = QPushButton("Criar/atualizar pastas (UTILS)")
        b_folders.clicked.connect(self._create_process_folders)
        b_login = QPushButton("Conectar UTILS…")
        b_login.clicked.connect(self._prompt_utils_login)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(self.btn_undo)
        row.addWidget(b_folders)
        row.addStretch(1)
        row.addWidget(b_login)
        lay.addLayout(row)

        lay.addWidget(QLabel("Atividade recente:"))
        self.recent = QPlainTextEdit()
        self.recent.setReadOnly(True)
        lay.addWidget(self.recent, 1)
        return w

    def _build_library_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # estado da navegação: importadores → processos → documentos
        self._lib_importer = None
        self._lib_folder = None
        self._lib_search = ""

        bar = QHBoxLayout()
        self.f_text = QLineEdit()
        self.f_text.setPlaceholderText(
            "buscar em TODA a biblioteca: nome / processo / importador…")
        self.f_text.returnPressed.connect(self._lib_run_search)
        b_search = QPushButton("Buscar")
        b_search.clicked.connect(self._lib_run_search)
        bar.addWidget(self.f_text, 1)
        bar.addWidget(b_search)
        lay.addLayout(bar)

        nav = QHBoxLayout()
        self.btn_lib_back = QPushButton("⬅ Voltar")
        self.btn_lib_back.clicked.connect(self._lib_back)
        self.lib_crumb = QLabel("")
        self.lib_crumb.setStyleSheet(T.LBL_SECTION)
        self.btn_lib_openfolder = QPushButton("Abrir pasta")
        self.btn_lib_openfolder.clicked.connect(self._lib_open_folder)
        b_refresh = QPushButton("Atualizar")
        b_refresh.clicked.connect(self._lib_reload)
        nav.addWidget(self.btn_lib_back)
        nav.addWidget(self.lib_crumb, 1)
        nav.addWidget(self.btn_lib_openfolder)
        nav.addWidget(b_refresh)
        lay.addLayout(nav)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.results = QTableWidget(0, 1)
        self.results.verticalHeader().setVisible(False)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.itemSelectionChanged.connect(self._lib_on_select)
        self.results.doubleClicked.connect(self._lib_open_row)
        split.addWidget(self.results)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.info = QLabel("Selecione um documento.")
        self.info.setStyleSheet(T.LBL_MUTED)
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        rl.addWidget(self.info)
        rowb = QHBoxLayout()
        b_open = QPushButton("Abrir")
        b_open.clicked.connect(self._open_selected)
        self.b_status = QPushButton("Marcar conferido")
        self.b_status.clicked.connect(self._toggle_status)
        rowb.addWidget(b_open)
        rowb.addWidget(self.b_status)
        rowb.addStretch(1)
        rl.addLayout(rowb)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_lbl = QLabel("—")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setWidget(self.preview_lbl)
        rl.addWidget(self.preview_scroll, 1)
        split.addWidget(right)
        split.setSizes([640, 480])
        lay.addWidget(split, 1)

        self._lib_reload()
        return w

    def _build_audit_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        row = QHBoxLayout()
        t = QLabel("Log de auditoria")
        t.setStyleSheet(T.LBL_PAGE_TITLE)
        row.addWidget(t)
        row.addStretch(1)
        b = QPushButton("Atualizar")
        b.clicked.connect(self._reload_audit)
        row.addWidget(b)
        lay.addLayout(row)
        self.audit = QTableWidget(0, 5)
        self.audit.setHorizontalHeaderLabels(["Quando", "Ação", "Detalhe", "De", "Para"])
        self.audit.verticalHeader().setVisible(False)
        self.audit.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audit.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.audit, 1)
        self._reload_audit()
        return w

    # ---- estado / workers ----
    def _refresh_status(self):
        n = self.db.cached_process_count()
        u = (f"UTILS online ({self.utils_client.username})"
             if self.utils_client else "UTILS offline")
        self.lbl_status.setText(
            f"Biblioteca: {self.library_root}\n{u} · {n} processo(s) em cache")

    def _log_recent(self, msg):
        self.recent.appendPlainText(f"[{datetime.now():%H:%M:%S}] {msg}")

    def _run(self, fn, on_done=None, on_fail=None):
        wk = Worker(fn)
        if on_done:
            wk.done.connect(on_done)
        if on_fail:
            wk.failed.connect(on_fail)
        wk.finished.connect(lambda: self._workers.remove(wk) if wk in self._workers else None)
        self._workers.append(wk)
        wk.start()

    # ---- integração UTILS (só-leitura) ----
    def _resolve_importer(self, ref):
        """Resolve importador: cache primeiro; depois UTILS (se online)."""
        if not ref:
            return None
        row = self.db.get_cached_process(ref)
        if row and row["importer"]:
            return row["importer"]
        if self.utils_client:
            try:
                for d in self.utils_client.list_processes(search=ref):
                    if str(d.get("reference", "")).upper() == ref:
                        self.db.upsert_processes([d])
                        return d.get("importer")
            except Exception:
                return None
        return None

    def _prompt_utils_login(self):
        dlg = utils_api.UtilsLoginDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.utils_client = dlg.client   # None se "Trabalhar offline"
            self._refresh_status()
            if self.utils_client:
                self._sync_cache()

    def _sync_cache(self):
        if not self.utils_client:
            return
        client = self.utils_client
        db = self.db

        def task():
            procs = client.list_processes()
            norm = [{
                "reference": d.get("reference"),
                "importer": d.get("importer"),
                "client_id": d.get("client_id"),
                "status": d.get("status"),
                "invoice_number": d.get("invoice_number"),
                "bl_number": d.get("bl_number"),
                "di_number": d.get("di_number"),
            } for d in procs if d.get("reference")]
            db.upsert_processes(norm)
            return len(norm)

        self._run(
            task,
            lambda n: (self._refresh_status(),
                       self._log_recent(f"UTILS: {n} processo(s) sincronizado(s).")),
            lambda e: self._log_recent(f"UTILS: falha ao sincronizar ({e})."))

    # ---- criar/atualizar pastas dos processos ----
    def _create_process_folders(self):
        """Pré-cria (ou renomeia) a pasta de cada processo do UTILS dentro da
        subpasta do importador, com o nome enriquecido REF[_fatura][_bl].
        Idempotente: já existindo, não duplica; se fatura/BL mudaram, renomeia."""
        if not self.utils_client and self.db.cached_process_count() == 0:
            QMessageBox.information(
                self, "Sem dados",
                "Não há processos em cache e o UTILS está offline.\n"
                "Conecte ao UTILS primeiro para puxar os processos.")
            return
        client = self.utils_client
        db = self.db
        lib = self.lib

        def task():
            if client:   # online: atualiza o cache antes (igual ao _sync_cache)
                procs = client.list_processes()
                norm = [{
                    "reference": d.get("reference"),
                    "importer": d.get("importer"),
                    "client_id": d.get("client_id"),
                    "status": d.get("status"),
                    "invoice_number": d.get("invoice_number"),
                    "bl_number": d.get("bl_number"),
                    "di_number": d.get("di_number"),
                } for d in procs if d.get("reference")]
                db.upsert_processes(norm)
            return lib.sync_process_folders(db.all_cached_processes())

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._run(task, self._on_folders_done, self._on_folders_fail)

    def _on_folders_fail(self, e):
        QApplication.restoreOverrideCursor()
        QMessageBox.critical(self, "Erro", f"Falha ao criar pastas: {e}")

    def _on_folders_done(self, report):
        QApplication.restoreOverrideCursor()
        nc = len(report["created"])
        nr = len(report["renamed"])
        for rel in report["created"]:
            self._log_recent(f"+ pasta criada: {rel}")
        for old_rel, new_rel in report["renamed"]:
            self._log_recent(f"↻ renomeada: {old_rel} → {new_rel}")
        for err in report["errors"]:
            self._log_recent(f"✗ {err}")
        msg = (f"{nc} pasta(s) criada(s), {nr} renomeada(s), "
               f"{report['skipped']} já em dia.")
        if report["no_importer"]:
            msg += f"\n{report['no_importer']} processo(s) sem importador (omitidos)."
        if report["errors"]:
            msg += (f"\n\n{len(report['errors'])} aviso(s):\n- "
                    + "\n- ".join(report["errors"][:8]))
            if len(report["errors"]) > 8:
                msg += f"\n… e mais {len(report['errors']) - 8}."
        (QMessageBox.warning if report["errors"] else QMessageBox.information)(
            self, "Pastas dos processos", msg)
        self._lib_reload()
        self._reload_audit()
        self._refresh_status()

    # ---- arquivamento ----
    def _archive_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Escolher arquivo(s) para arquivar", str(Path.home()))
        if paths:
            self._start_archive(paths)

    def _archive_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, "Escolher pasta para arquivar", str(Path.home()))
        if not d:
            return
        root = Path(d)
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            children = []
        subdirs = [p for p in children if p.is_dir() and not p.name.startswith(".")]
        loose = [p for p in children if p.is_file() and not p.name.startswith(".")]

        # Sem subpastas: arquiva os arquivos soltos (comportamento de sempre).
        if not subdirs:
            files = [str(p) for p in loose]
            if not files:
                QMessageBox.information(self, "Vazio", "Nenhum arquivo na pasta.")
                return
            self._start_archive(files)
            return

        # Com subpastas: deixa escolher quais entram (ignorar as que não são processo).
        # A detecção é pelo NOME da subpasta (não pelo caminho), pra a pasta-mãe não
        # "contaminar" todas as subpastas com o processo dela.
        matcher = ProcessMatcher(self.db.all_cached_processes())
        entries = []
        for sub in subdirs:
            m = matcher.match(sub.name)
            entries.append({"path": sub, "name": sub.name,
                            "process": m.reference if m else "",
                            "count": self._count_docs(sub, recursive=True),
                            "loose": False})
        if loose:
            entries.append({"path": root, "name": "(arquivos soltos nesta pasta)",
                            "process": "", "count": len(loose), "loose": True})

        dlg = FolderPickDialog(entries, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        files = []
        for i in dlg.selected_indices:
            e = entries[i]
            if e["loose"]:
                files += [str(p) for p in e["path"].iterdir()
                          if p.is_file() and not p.name.startswith(".")]
            else:
                files += [str(p) for p in e["path"].rglob("*")
                          if p.is_file() and not p.name.startswith(".")]
        if not files:
            QMessageBox.information(
                self, "Nada selecionado",
                "Nenhuma subpasta marcada — nada foi arquivado.")
            return
        self._start_archive(files)

    def _start_archive(self, paths):
        root = str(Path(self.library_root).resolve())
        clean = []
        for p in paths:
            try:
                if str(Path(p).resolve()).startswith(root):
                    continue   # já está dentro da biblioteca
            except OSError:
                continue
            clean.append(p)
        if not clean:
            QMessageBox.information(
                self, "Nada a fazer",
                "Os arquivos selecionados já estão na biblioteca.")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            # casa por processo/fatura/BL usando o cache de processos do UTILS
            matcher = ProcessMatcher(self.db.all_cached_processes())
            proposals = [build_proposal(p, matcher=matcher,
                                        resolver=self._resolve_importer)
                         for p in clean]
        finally:
            QApplication.restoreOverrideCursor()

        dlg = TriageDialog(proposals, self.db.list_importers(),
                           self._resolve_importer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._do_commit(dlg.result_rows)

    def _do_commit(self, rows):
        lib = self.lib

        def task():
            out, errors = [], []
            for path, ref, imp, dtype in rows:
                if not Path(path).exists():
                    continue
                try:
                    out.append(lib.commit(path, imp, ref, dtype))
                except Exception as e:
                    # move seguro falhou → origem preservada; segue os demais
                    errors.append(f"{Path(path).name}: {e}")
            return out, errors

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._run(task, self._on_archive_done, self._on_archive_fail)

    def _on_archive_fail(self, e):
        QApplication.restoreOverrideCursor()
        QMessageBox.critical(self, "Erro", f"Falha ao arquivar: {e}")

    def _on_archive_done(self, payload):
        QApplication.restoreOverrideCursor()
        results, errors = payload
        self.last_results = results
        ing = sum(1 for r in results if r.status == "ingested")
        dup = sum(1 for r in results if r.status == "duplicate")
        for r in results:
            if r.status == "ingested":
                self._log_recent(
                    f"✓ {r.original_name} → {r.importer}/{r.process_ref} [{r.doc_type}]")
            else:
                self._log_recent(
                    f"⊘ {r.original_name}: duplicado de {r.dup_process or '?'} → _duplicados")
        for e in errors:
            self._log_recent(f"✗ {e}")
        self.btn_undo.setEnabled(bool(results))
        msg = f"{ing} arquivado(s)."
        if dup:
            msg += (f" {dup} duplicado(s) movido(s) para _duplicados "
                    "(não duplicados na biblioteca).")
        if errors:
            msg += (f"\n\n{len(errors)} falha(s) — a origem foi preservada:\n- "
                    + "\n- ".join(errors[:8]))
            if len(errors) > 8:
                msg += f"\n… e mais {len(errors) - 8}."
        (QMessageBox.warning if errors else QMessageBox.information)(
            self, "Concluído", msg)
        self._lib_reload()
        self._reload_audit()
        self._refresh_status()

    def _undo_last(self):
        if not self.last_results:
            return
        q = QMessageBox.question(
            self, "Desfazer",
            f"Desfazer o último arquivamento ({len(self.last_results)} item(s))?\n"
            "Os arquivos voltam para o local de origem.")
        if q != QMessageBox.StandardButton.Yes:
            return
        ok = 0
        for r in reversed(self.last_results):
            try:
                if self.lib.undo(r):
                    ok += 1
            except Exception as e:
                self._log_recent(f"Falha no undo de {r.original_name}: {e}")
        self._log_recent(f"Desfeito: {ok} item(s) devolvido(s) à origem.")
        self.last_results = []
        self.btn_undo.setEnabled(False)
        self._lib_reload()
        self._reload_audit()
        self._refresh_status()

    # ---- biblioteca: navegação por pastas (importador → processo → docs) ----
    def _lib_level(self):
        if self._lib_search:
            return "busca"
        if self._lib_importer is None:
            return "importadores"
        if self._lib_folder is None:
            return "processos"
        return "documentos"

    def _lib_dirs(self, path, exclude=()):
        try:
            names = [p.name for p in path.iterdir()
                     if p.is_dir() and not p.name.startswith(".")
                     and p.name not in exclude]
        except OSError:
            return []
        return sorted(names, key=str.lower)

    @staticmethod
    def _count_docs(path, recursive):
        n = 0
        try:
            it = path.rglob("*") if recursive else path.iterdir()
            for p in it:
                if p.is_file() and not p.name.startswith("."):
                    n += 1
        except OSError:
            pass
        return n

    def _lib_cur_folder(self):
        """Pasta no disco do nível atual (p/ o botão 'Abrir pasta')."""
        root = self.lib.root
        if self._lib_importer is None:
            return root
        if self._lib_folder is None:
            return root / self._lib_importer
        return root / self._lib_importer / self._lib_folder

    def _lib_run_search(self):
        self._lib_search = self.f_text.text().strip()
        self._lib_reload()

    def _lib_back(self):
        if self._lib_search:
            self._lib_search = ""
            self.f_text.clear()
        elif self._lib_folder is not None:
            self._lib_folder = None
        elif self._lib_importer is not None:
            self._lib_importer = None
        self._lib_reload()

    def _lib_open_folder(self):
        # na busca, abre a pasta do doc selecionado (se houver); senão a pasta atual
        if self._lib_search:
            kind, payload, _ = self._lib_selected()
            if kind == "doc":
                open_path(Path(payload).parent)
                return
        open_path(self._lib_cur_folder())

    def _setup_cols(self, headers, stretch_col):
        self.results.setColumnCount(len(headers))
        self.results.setHorizontalHeaderLabels(headers)
        h = self.results.horizontalHeader()
        for c in range(len(headers)):
            h.setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch if c == stretch_col
                else QHeaderView.ResizeMode.ResizeToContents)

    def _lib_reload(self):
        level = self._lib_level()
        self._clear_preview()
        self.btn_lib_back.setEnabled(level != "importadores")
        if level == "busca":
            self.lib_crumb.setText(f"Busca: “{self._lib_search}”")
            self._lib_render_search(self._lib_search)
        elif level == "importadores":
            self.lib_crumb.setText("Biblioteca")
            self._lib_render_importers()
        elif level == "processos":
            self.lib_crumb.setText(f"Biblioteca  ›  {self._lib_importer}")
            self._lib_render_dirs(self.lib.root / self._lib_importer, "processo")
        else:
            self.lib_crumb.setText(
                f"Biblioteca  ›  {self._lib_importer}  ›  {self._lib_folder}")
            self._lib_render_docs(self._lib_importer, self._lib_folder)

    def _set_dir_row(self, i, name, count_text):
        it = QTableWidgetItem(f"📁  {name}")
        it.setData(Qt.ItemDataRole.UserRole, ("dir", name))
        self.results.setItem(i, 0, it)
        self.results.setItem(i, 1, QTableWidgetItem(count_text))

    def _lib_render_importers(self):
        names = self._lib_dirs(self.lib.root, exclude={QUARANTINE})
        self._setup_cols(["Importador", "Conteúdo"], 0)
        self.results.setRowCount(len(names))
        for i, name in enumerate(names):
            n = self._count_docs(self.lib.root / name, recursive=True)
            self._set_dir_row(i, name, f"{n} doc(s)")
        self.info.setText(
            f"{len(names)} importador(es). Abra um (duplo-clique) para ver os processos.")

    def _lib_render_dirs(self, parent, kind):
        names = self._lib_dirs(parent)
        self._setup_cols([f"Pasta ({kind})", "Conteúdo"], 0)
        self.results.setRowCount(len(names))
        for i, name in enumerate(names):
            n = self._count_docs(parent / name, recursive=False)
            self._set_dir_row(i, name, f"{n} doc(s)")
        self.info.setText(
            f"{len(names)} pasta(s). Abra uma (duplo-clique) para ver os documentos.")

    def _lib_render_docs(self, importer, folder):
        folder_abs = self.lib.root / importer / folder
        try:
            files = sorted([p for p in folder_abs.iterdir()
                            if p.is_file() and not p.name.startswith(".")],
                           key=lambda p: p.name.lower())
        except OSError:
            files = []
        self._setup_cols(["Arquivo", "Tipo", "Status", "Tamanho"], 0)
        self.results.setRowCount(len(files))
        for i, p in enumerate(files):
            rel = f"{importer}/{folder}/{p.name}"
            r = self.db.get_by_rel_path(rel)
            dtype = DOC_TYPE_LABELS.get(r["doc_type"], r["doc_type"] or "") if r else ""
            status = r["status"] if r else "(fora do índice)"
            size = r["size_bytes"] if r else p.stat().st_size
            it = QTableWidgetItem(f"📄  {p.name}")
            it.setData(Qt.ItemDataRole.UserRole, ("doc", str(p)))
            it.setData(Qt.ItemDataRole.UserRole + 1, r["id"] if r else None)
            self.results.setItem(i, 0, it)
            self.results.setItem(i, 1, QTableWidgetItem(dtype))
            self.results.setItem(i, 2, QTableWidgetItem(status))
            self.results.setItem(i, 3, QTableWidgetItem(human_size(size)))
        self.info.setText(f"{len(files)} documento(s) nesta pasta. Clique para pré-visualizar.")

    def _lib_render_search(self, query):
        rows = self.db.search(text=query)
        self._setup_cols(
            ["Importador", "Processo", "Tipo", "Arquivo", "Status", "Tamanho"], 3)
        self.results.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name = r["original_name"] or Path(r["rel_path"]).name
            vals = [r["importer"] or "", r["process_ref"] or "",
                    DOC_TYPE_LABELS.get(r["doc_type"], r["doc_type"] or ""),
                    name, r["status"] or "", human_size(r["size_bytes"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 0:   # marcador do doc fica sempre na col 0
                    it.setData(Qt.ItemDataRole.UserRole,
                               ("doc", str(self.lib.abs_path(r["rel_path"]))))
                    it.setData(Qt.ItemDataRole.UserRole + 1, r["id"])
                self.results.setItem(i, c, it)
        self.info.setText(f"{len(rows)} documento(s) encontrados.")

    def _lib_selected(self):
        """(kind, payload, doc_id) da linha selecionada. kind: 'dir'|'doc'|None."""
        row = self.results.currentRow()
        if row < 0:
            return (None, None, None)
        it = self.results.item(row, 0)
        data = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not data:
            return (None, None, None)
        return (data[0], data[1], it.data(Qt.ItemDataRole.UserRole + 1))

    def _lib_open_row(self, *args):
        kind, payload, _ = self._lib_selected()
        if kind == "dir":
            if self._lib_importer is None:
                self._lib_importer = payload
            elif self._lib_folder is None:
                self._lib_folder = payload
            self._lib_reload()
        elif kind == "doc":
            open_path(payload)

    def _clear_preview(self):
        self.preview_lbl.setPixmap(QPixmap())
        self.preview_lbl.setText("—")
        self.info.setText("Selecione um documento.")
        self.b_status.setEnabled(False)

    def _lib_on_select(self):
        kind, payload, did = self._lib_selected()
        if kind != "doc":
            self.b_status.setEnabled(False)
            return
        if did:
            r = self.db.get_document(did)
            if r:
                self.info.setText(
                    f"<b>{r['original_name']}</b><br>{r['importer']} / {r['process_ref']} · "
                    f"{DOC_TYPE_LABELS.get(r['doc_type'], r['doc_type'] or '')}<br>"
                    f"Status: {r['status']} · {human_size(r['size_bytes'])}<br>"
                    f"<span style='color:{T.TEXT_MUTED}'>{r['rel_path']}</span>")
                self.b_status.setEnabled(True)
                self.b_status.setText(
                    "Marcar recebido" if r["status"] == "conferido" else "Marcar conferido")
        else:
            p = Path(payload)
            size = p.stat().st_size if p.exists() else 0
            self.info.setText(
                f"<b>{p.name}</b><br><span style='color:{T.TEXT_MUTED}'>"
                f"(arquivo solto, fora do índice)</span><br>{human_size(size)}")
            self.b_status.setEnabled(False)
        self._show_preview(payload)

    def _show_preview(self, path):
        if not Path(path).exists():
            self.preview_lbl.setPixmap(QPixmap())
            self.preview_lbl.setText("(arquivo não encontrado)")
            return
        pix = render_preview(path)
        if pix is None:
            self.preview_lbl.setPixmap(QPixmap())
            self.preview_lbl.setText("(sem preview para este tipo)\n" + Path(path).name)
        else:
            self.preview_lbl.setText("")
            self.preview_lbl.setPixmap(
                pix.scaledToWidth(min(pix.width(), 900),
                                  Qt.TransformationMode.SmoothTransformation))

    def _open_selected(self):
        kind, payload, _ = self._lib_selected()
        if kind == "doc":
            open_path(payload)

    def _toggle_status(self):
        kind, payload, did = self._lib_selected()
        if kind != "doc" or not did:
            return
        r = self.db.get_document(did)
        new = "recebido" if r["status"] == "conferido" else "conferido"
        self.db.set_status(did, new)
        self.db.log("status", r["sha256"], detail=f"{r['original_name']} → {new}")
        self._lib_reload()
        self._reload_audit()

    # ---- auditoria ----
    def _reload_audit(self):
        rows = self.db.list_audit(300)
        self.audit.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["ts"], r["action"], r["detail"] or "",
                    Path(r["from_path"]).name if r["from_path"] else "",
                    Path(r["to_path"]).name if r["to_path"] else ""]
            for c, v in enumerate(vals):
                self.audit.setItem(i, c, QTableWidgetItem(str(v)))

    def _on_tab_changed(self, idx):
        if idx == 1:
            self._lib_reload()
        elif idx == 2:
            self._reload_audit()

    def closeEvent(self, e):
        try:
            self.db.close()
        except Exception:
            pass
        super().closeEvent(e)


# ── arranque ──────────────────────────────────────────────────────
def ensure_library_root():
    """Garante a raiz da biblioteca; pergunta no 1º uso. None = cancelar."""
    root = config.get_library_root()
    if root and Path(root).expanduser().exists():
        return str(Path(root).expanduser())

    default = config.DEFAULT_LIBRARY_ROOT
    box = QMessageBox()
    box.setStyleSheet(T.MAIN_STYLESHEET)
    box.setWindowTitle("IHS INBOX — Biblioteca")
    box.setText("Onde fica a biblioteca de documentos?")
    box.setInformativeText(f"Padrão sugerido:\n{default}")
    use_default = box.addButton("Usar padrão", QMessageBox.ButtonRole.AcceptRole)
    choose = box.addButton("Escolher pasta…", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Sair", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked == use_default:
        root = default
    elif clicked == choose:
        d = QFileDialog.getExistingDirectory(
            None, "Escolher pasta da biblioteca", str(Path.home()))
        if not d:
            return None
        root = d
    else:
        return None
    Path(root).expanduser().mkdir(parents=True, exist_ok=True)
    config.set_library_root(root)
    return str(Path(root).expanduser())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("IHS INBOX")
    app.setDesktopFileName("ihs-inbox")   # casa com StartupWMClass=ihs-inbox
    app.setStyleSheet(T.MAIN_STYLESHEET)

    logo = Path(__file__).parent / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))

    root = ensure_library_root()
    if not root:
        return

    win = MainWindow(root)
    if logo.exists():
        win.setWindowIcon(QIcon(str(logo)))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
