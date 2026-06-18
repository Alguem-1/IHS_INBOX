"""
worker.py — Roda uma função numa thread separada (rede/hash) sem travar a UI.
Espelha o padrão usado nos apps irmãos.
"""

from PyQt6.QtCore import QThread, pyqtSignal


class Worker(QThread):
    done = pyqtSignal(object)             # resultado da função
    failed = pyqtSignal(str)              # mensagem de erro
    progress = pyqtSignal(int, int, str)  # feitos, total, rótulo do item atual

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        # Quando True, a fn recebe um callback report(feitos, total, rótulo) como
        # 1º argumento, p/ emitir progresso (sinal entregue na thread da UI).
        self.wants_progress = False

    def run(self):
        try:
            if self.wants_progress:
                result = self._fn(self.progress.emit, *self._args, **self._kwargs)
            else:
                result = self._fn(*self._args, **self._kwargs)
            self.done.emit(result)
        except Exception as e:  # reporta qualquer falha à UI
            self.failed.emit(str(e))
