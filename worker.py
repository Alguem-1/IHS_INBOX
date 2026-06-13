"""
worker.py — Roda uma função numa thread separada (rede/hash) sem travar a UI.
Espelha o padrão usado nos apps irmãos.
"""

from PyQt6.QtCore import QThread, pyqtSignal


class Worker(QThread):
    done = pyqtSignal(object)    # resultado da função
    failed = pyqtSignal(str)     # mensagem de erro

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:  # reporta qualquer falha à UI
            self.failed.emit(str(e))
