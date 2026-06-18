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

# Casamento por fatura/BL: ids menores que isso (após normalizar) são ignorados,
# pra não dar falso positivo com números curtos soltos no nome.
_MIN_ID_LEN = 5


def _norm(s) -> str:
    """Reduz a só alfanuméricos minúsculos: 'INV-12345' / 'INV 12345' → 'inv12345'."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _tokens(text) -> set:
    """Pedaços alfanuméricos do texto, já normalizados (p/ casamento exato)."""
    return {t for t in (_norm(p) for p in re.split(r"[^A-Za-z0-9]+", text or "")) if t}

# Tipos canônicos do INBOX. Os que coincidem com o IHS_UTILS usam a MESMA chave
# (INVOICE / PACKING_LIST / BL), p/ um futuro checklist mapear limpo.
DOC_TYPES = [
    "INVOICE", "NOTA_FISCAL", "PACKING_LIST", "BL", "DI", "DTA", "CAPA",
    "FECHAMENTO", "EXTRATO", "AFRMM", "CI", "SEGURO", "PHYTO_CERTIFICATE",
    "FUMIGATION", "CERTIFICADO", "OUTRO",
]

DOC_TYPE_LABELS = {
    "INVOICE": "Invoice",
    "NOTA_FISCAL": "Nota Fiscal",
    "PACKING_LIST": "Packing List",
    "BL": "B/L (Conhecimento)",
    "DI": "DI / DUIMP",
    "DTA": "DTA",
    "CAPA": "Capa",
    "FECHAMENTO": "Fechamento",
    "EXTRATO": "Extrato",
    "AFRMM": "AFRMM",
    "CI": "CI",
    "SEGURO": "Seguro",
    "PHYTO_CERTIFICATE": "Certificado Fitossanitário",
    "FUMIGATION": "Certificado de Fumigação",
    "CERTIFICADO": "Certificado",
    "OUTRO": "Outro",
}

# Palavras-chave → tipo. Ordem importa: mais específicas primeiro.
_KEYWORDS = [
    ("PACKING_LIST", ("packing", "romaneio", " pl", "pl_", "_pl")),
    ("INVOICE", ("invoice", "fatura", "comercial", "_inv", "inv_")),
    ("NOTA_FISCAL", ("nota fiscal", "nota_fiscal", "notafiscal", " nf", "_nf", "-nf")),
    ("BL", ("bill of lading", "conhecimento", "awb", " bl", "bl_", "_bl", "b-l", "b_l")),
    ("DI", ("duimp", "declaracao", "declaração", " di", "di_", "_di")),
    # DTA/AFRMM: acrônimos com fronteira (espaço/_/-) p/ não dar falso positivo
    ("DTA", (" dta", "dta_", "_dta", "dta-", "-dta")),
    ("FECHAMENTO", ("fechamento", "fech")),
    ("CAPA", ("capa",)),
    ("EXTRATO", ("extrato",)),
    ("AFRMM", ("afrmm",)),
    ("SEGURO", ("seguro", "apolice", "apólice", "insurance")),
    # phyto e fumigação ANTES do certificado genérico (mais específico vence)
    ("PHYTO_CERTIFICATE", ("fitossanit", "phytosanit", "fito", "phyto")),
    ("FUMIGATION", ("fumiga",)),   # fumigation / fumigação / fumigacao
    ("CERTIFICADO", ("certificad", "certificate", "origem")),
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
class Match:
    """Processo casado para um arquivo, e COMO foi casado (p/ mostrar ao humano)."""
    reference: str
    importer: str
    matched_by: str   # "processo" | "fatura" | "bl"
    via: str = ""     # o identificador que casou (ex.: 'INV12345')


class ProcessMatcher:
    """Acha o processo de um arquivo pelo NOME, usando identificadores que já
    conhecemos do UTILS (cache): nº do processo, depois fatura, depois BL.

    Não interpreta conteúdo fiscal — só procura, no nome do arquivo/pasta,
    identificadores que o UTILS já nos deu. É roteamento, não leitura de dado."""

    def __init__(self, cached_rows=None):
        self.importer_by_ref = {}        # REF -> importador (p/ casamento por regex)
        self.invoices = []               # [(norm_id, reference, importador)]
        self.bls = []
        for r in cached_rows or []:
            ref = (r["reference"] or "").strip().upper() if r["reference"] else ""
            if not ref:
                continue
            imp = (r["importer"] or "").strip() if r["importer"] else ""
            self.importer_by_ref[ref] = imp
            inv = _norm(r["invoice_number"])
            if len(inv) >= _MIN_ID_LEN:
                self.invoices.append((inv, ref, imp))
            bl = _norm(r["bl_number"])
            if len(bl) >= _MIN_ID_LEN:
                self.bls.append((bl, ref, imp))

    @staticmethod
    def _match_ids(ids, norm_text, tokens):
        """Casa por token exato (preferido) e, na falta, por substring. Se mais de
        um processo casar, devolve None (ambíguo: melhor o humano decidir)."""
        for picker in (lambda nid: nid in tokens, lambda nid: nid in norm_text):
            hits = [(ref, imp, nid) for nid, ref, imp in ids if picker(nid)]
            refs = {h[0] for h in hits}
            if len(refs) == 1:
                return hits[0]
            if len(refs) > 1:
                return None   # ambíguo neste nível — não cai pro próximo
        return None

    def match(self, text) -> "Match | None":
        norm_text = _norm(text)
        tokens = _tokens(text)
        ref = extract_process_ref(text)            # 1) processo (mais forte)
        if ref:
            return Match(ref, self.importer_by_ref.get(ref, ""), "processo", ref)
        hit = self._match_ids(self.invoices, norm_text, tokens)   # 2) fatura
        if hit:
            return Match(hit[0], hit[1], "fatura", hit[2])
        hit = self._match_ids(self.bls, norm_text, tokens)        # 3) BL
        if hit:
            return Match(hit[0], hit[1], "bl", hit[2])
        return None


@dataclass
class Proposal:
    """Arquivamento proposto p/ um arquivo — tudo editável pelo humano."""
    path: str
    original_name: str
    process_ref: str = ""
    importer: str = ""
    doc_type: str = "OUTRO"
    importer_resolved: bool = False   # True se o importador veio do UTILS/cache
    matched_by: str = ""              # como o processo foi achado (processo/fatura/bl)
    matched_via: str = ""             # o identificador que casou
    subdir: str = ""                  # subcaminho a preservar dentro da pasta do processo


def build_proposal(path: str, matcher=None, resolver=None) -> Proposal:
    """Monta a proposta a partir do NOME (e pastas-pai) do arquivo.
    `matcher` (ProcessMatcher) acha o processo por processo/fatura/BL; `resolver(ref)
    -> importer|None` é o fallback ao vivo p/ o importador (UTILS/cache).
    Sem matcher → comportamento antigo (regex de processo só no nome)."""
    name = Path(path).name
    prop = Proposal(path=path, original_name=name, doc_type=guess_doc_type(name))

    m = matcher.match(path) if matcher else None
    if m is None:
        ref = extract_process_ref(name)   # sem cache: regex no nome (retrocompat)
        if ref:
            m = Match(ref, "", "processo", ref)
    if m:
        prop.process_ref = m.reference
        prop.matched_by = m.matched_by
        prop.matched_via = m.via
        if m.importer:
            prop.importer = m.importer
            prop.importer_resolved = True

    if prop.process_ref and not prop.importer and resolver:
        importer = resolver(prop.process_ref)
        if importer:
            prop.importer = importer
            prop.importer_resolved = True
    return prop
