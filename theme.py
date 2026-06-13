"""
theme.py — Paleta e estilos dark do IHS_INBOX (#050505), no padrão da suíte IHS.
Importado como `import theme as T` pelos outros módulos.
"""

# ── Paleta ────────────────────────────────────────────────────────
BG         = "#050505"
BG_PANEL   = "#0c0e0c"
BG_INPUT   = "#121412"
BG_HOVER   = "#1b1f1b"
BORDER     = "#232823"
TEXT       = "#d8e2d8"
TEXT_MUTED = "#7c877c"
ACCENT     = "#46d17a"
ACCENT_DIM = "#1e6b40"
RED        = "#e0524e"
YELLOW     = "#e0b84e"
GREEN      = "#46d17a"

MAIN_STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget {{ background: {BG}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel {{ background: transparent; }}

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {BG_HOVER};
}}

QPushButton {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: {BG_HOVER}; border-color: {ACCENT_DIM}; }}
QPushButton:pressed {{ background: {BG_INPUT}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 18px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QTableWidget, QTreeWidget, QListWidget, QTableView, QTreeView {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT};
    outline: none;
}}
QHeaderView::section {{
    background: {BG};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
}}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {BG_HOVER};
}}

QMenu {{ background: {BG_PANEL}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {BG_HOVER}; }}

QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

QToolTip {{ background: {BG_PANEL}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""

# ── Estilos nomeados (uso inline) ─────────────────────────────────
BTN_PRIMARY = f"""
QPushButton {{
    background: {ACCENT_DIM};
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT}; color: {BG}; }}
QPushButton:disabled {{ background: {BG_PANEL}; border-color: {BORDER}; color: {TEXT_MUTED}; }}
"""

LBL_PAGE_TITLE = f"color: {TEXT}; font-size: 20px; font-weight: 700;"
LBL_SECTION    = f"color: {ACCENT}; font-size: 11px; font-weight: 600; letter-spacing: 1px;"
LBL_MUTED      = f"color: {TEXT_MUTED}; font-size: 12px;"
LBL_HINT       = f"color: {TEXT_MUTED}; font-size: 11px;"
