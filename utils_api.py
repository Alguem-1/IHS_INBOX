"""
utils_api.py — Cliente SÓ-LEITURA do IHS_UTILS para o INBOX.

Cópia mínima do necessário (login + leitura). NÃO importa o api_client.py do
UTILS de propósito: assim é estruturalmente impossível chamar create/update/
delete e o INBOX não acopla no código do outro projeto. Regra de ouro: o INBOX
NUNCA escreve no banco do UTILS.
"""

import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel,
)

import config
import theme as T


class UtilsError(Exception):
    pass


class ReadOnlyUtilsClient:
    """Fala com a API do IHS_UTILS usando SÓ endpoints de leitura."""

    _TIMEOUT = (6, 20)   # (connect, read) curto p/ não travar a UI

    def __init__(self, server_url: str, token: str, username: str = ""):
        self.server_url = server_url.rstrip("/")
        self._token = token
        self.username = username
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, **params):
        r = self._session.get(
            f"{self.server_url}{path}",
            params={k: v for k, v in params.items() if v is not None},
            timeout=self._TIMEOUT)
        if r.status_code == 401:
            raise UtilsError("Sessão expirada — conecte novamente.")
        if not r.ok:
            raise UtilsError(f"Erro do servidor ({r.status_code}).")
        return r.json()

    # — só leitura —
    def list_processes(self, search=None, status=None, client_id=None) -> list[dict]:
        data = self._get("/processes", search=search, status=status,
                         client_id=client_id)
        if isinstance(data, dict) and "items" in data:   # servidor paginado
            data = data["items"]
        return data

    def get_process(self, process_id: int) -> dict:
        return self._get(f"/processes/{process_id}")

    def list_importadores(self) -> list[dict]:
        return self._get("/importadores")


def login(server_url: str, username: str, password: str) -> dict:
    """POST /auth/login → {access_token, username, is_admin}."""
    r = requests.post(f"{server_url.rstrip('/')}/auth/login",
                      data={"username": username, "password": password},
                      timeout=8)
    if r.status_code == 401:
        raise UtilsError("Usuário ou senha incorretos.")
    if not r.ok:
        raise UtilsError(f"Erro do servidor: {r.status_code}")
    payload = r.json()
    if not payload.get("access_token"):
        raise UtilsError("Resposta inválida do servidor.")
    return payload


class UtilsLoginDialog(QDialog):
    """
    Login só-leitura no IHS_UTILS. server_url/usuário pré-preenchidos da config
    do cliente do UTILS (~/.ihs_utils/client_config.json). O botão 'Trabalhar
    offline' pula direto pro cache local. Após exec(): .client (ou None) e
    .offline.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IHS INBOX — Conectar ao IHS_UTILS (só-leitura)")
        self.setFixedWidth(460)
        self.setStyleSheet(T.MAIN_STYLESHEET)
        self.client = None
        self.offline = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(14)

        title = QLabel("Conectar ao IHS_UTILS")
        title.setStyleSheet(T.LBL_PAGE_TITLE)
        lay.addWidget(title)
        sub = QLabel("Só leitura — usado para descobrir o importador do "
                     "processo. Funciona offline pelo cache se você pular.")
        sub.setStyleSheet(T.LBL_HINT)
        sub.setWordWrap(True)
        lay.addWidget(sub)

        form = QFormLayout()
        form.setSpacing(10)
        self.inp_server = QLineEdit(config.get_utils_server_url())
        self.inp_server.setPlaceholderText("https://servidor…")
        self.inp_user = QLineEdit(config.get_utils_last_username())
        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pass.returnPressed.connect(self._do_login)
        form.addRow("Servidor:", self.inp_server)
        form.addRow("Usuário:", self.inp_user)
        form.addRow("Senha:", self.inp_pass)
        lay.addLayout(form)

        self.lbl_err = QLabel("")
        self.lbl_err.setStyleSheet(f"color:{T.RED}; font-size:11px;")
        self.lbl_err.setWordWrap(True)
        self.lbl_err.hide()
        lay.addWidget(self.lbl_err)

        row = QHBoxLayout()
        btn_off = QPushButton("Trabalhar offline")
        btn_off.clicked.connect(self._go_offline)
        self.btn_login = QPushButton("Conectar")
        self.btn_login.setStyleSheet(T.BTN_PRIMARY)
        self.btn_login.clicked.connect(self._do_login)
        row.addWidget(btn_off)
        row.addStretch(1)
        row.addWidget(self.btn_login)
        lay.addLayout(row)

        self.inp_pass.setFocus() if config.get_utils_last_username() else self.inp_user.setFocus()

    def _err(self, msg):
        self.lbl_err.setText(msg)
        self.lbl_err.show()

    def _go_offline(self):
        self.offline = True
        self.client = None
        self.accept()

    def _do_login(self):
        server = self.inp_server.text().strip().rstrip("/")
        user = self.inp_user.text().strip()
        pwd = self.inp_pass.text()
        if not (server and user and pwd):
            self._err("Preencha servidor, usuário e senha (ou use offline).")
            return
        self.btn_login.setEnabled(False)
        self.btn_login.setText("Conectando…")
        self.lbl_err.hide()
        try:
            payload = login(server, user, pwd)
            self.client = ReadOnlyUtilsClient(
                server, payload["access_token"], payload.get("username", user))
            config.save_utils_login(server, user)
            self.accept()
        except UtilsError as e:
            self._err(str(e))
        except requests.exceptions.ConnectionError:
            self._err("Não foi possível conectar. Verifique o servidor ou use offline.")
        except requests.exceptions.Timeout:
            self._err("Tempo esgotado. Tente de novo ou use offline.")
        except Exception as e:
            self._err(f"Erro inesperado: {e}")
        finally:
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Conectar")
