"""
intake.py — Triagem: extrai o nº do processo (IHS\\d{3}-\\d{2}) do nome do
arquivo e palpita o tipo do documento por palavra-chave. SÓ etiqueta — nunca lê
o conteúdo. `build_proposal()` é o ponto único de entrada: hoje chamado pelo
arquivamento manual; amanhã, pelo watcher de pasta-isca.
"""

import re
from dataclasses import dataclass
from pathlib import Path

PROCESS_RE = re.compile(r"IHS\d{3}-\d{2}", re.IGNORECASE)

# Tipos canônicos do INBOX. Os que coincidem com o IHS_UTILS usam a MESMA chave
# (INVOICE / PACKING_LIST / BL), p/ um futuro checklist mapear limpo.
DOC_TYPES = [
    "INVOICE", "PACKING_LIST", "BL", "DI", "CAPA", "FECHAMENTO",
    "EXTRATO", "CI", "SEGURO", "CERTIFICADO", "OUTRO",
]

DOC_TYPE_LABELS = {
    "INVOICE": "Invoice",
    "PACKING_LIST": "Packing List",
    "BL": "B/L (Conhecimento)",
    "DI": "DI / DUIMP",
    "CAPA": "Capa",
    "FECHAMENTO": "Fechamento",
    "EXTRATO": "Extrato",
    "CI": "CI",
    "SEGURO": "Seguro",
    "CERTIFICADO": "Certificado",
    "OUTRO": "Outro",
}

# Palavras-chave → tipo. Ordem importa: mais específicas primeiro.
_KEYWORDS = [
    ("PACKING_LIST", ("packing", "romaneio", " pl", "pl_", "_pl")),
    ("INVOICE", ("invoice", "fatura", "comercial", "_inv", "inv_")),
    ("BL", ("bill of lading", "conhecimento", "awb", " bl", "bl_", "_bl", "b-l", "b_l")),
    ("DI", ("duimp", "declaracao", "declaração", " di", "di_", "_di")),
    ("FECHAMENTO", ("fechamento", "fech")),
    ("CAPA", ("capa",)),
    ("EXTRATO", ("extrato",)),
    ("SEGURO", ("seguro", "apolice", "apólice", "insurance")),
    ("CERTIFICADO", ("certificad", "certificate", "fito", "phyto", "origem")),
    ("CI", (" ci", "ci_", "_ci")),
]


def extract_process_ref(name: str) -> str | None:
    m = PROCESS_RE.search(name or "")
    return m.group(0).upper() if m else None


def guess_doc_type(name: str) -> str:
    low = f" {(name or '').lower()} "
    for doc_type, keys in _KEYWORDS:
        for k in keys:
            if k in low:
                return doc_type
    return "OUTRO"


@dataclass
class Proposal:
    """Arquivamento proposto p/ um arquivo — tudo editável pelo humano."""
    path: str
    original_name: str
    process_ref: str = ""
    importer: str = ""
    doc_type: str = "OUTRO"
    importer_resolved: bool = False   # True se o importador veio do UTILS/cache


def build_proposal(path: str, resolver=None) -> Proposal:
    """Monta a proposta a partir do NOME do arquivo. `resolver(ref) ->
    importer|None` resolve o importador (cache do UTILS / API)."""
    name = Path(path).name
    ref = extract_process_ref(name) or ""
    prop = Proposal(path=path, original_name=name, process_ref=ref,
                    doc_type=guess_doc_type(name))
    if ref and resolver:
        importer = resolver(ref)
        if importer:
            prop.importer = importer
            prop.importer_resolved = True
    return prop
