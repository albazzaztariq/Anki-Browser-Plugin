"""
AJS Anki Add-on — ui/preview.py
PyQt6 dialog that displays the pending card's fields before the note is committed.

All fields are editable so the user can correct LLM errors before the card is
saved (FR-14).  The dialog has two buttons:
  - "Add Card"  → accepted  (QDialog.Accepted)
  - "Skip"      → rejected  (QDialog.Rejected)

The dialog uses PyQt6 as bundled with Anki 23.x+.  No external packages needed.

Fields displayed (FR-12):
  - Word (kanji)
  - Reading (hiragana)
  - Part of speech
  - Definition (English)
  - Example sentence (Japanese)
  - Audio path (display only — shows filename or "none")
  - Source URL (display only)
"""

import sys
from pathlib import Path

try:
    from PyQt6.QtWidgets import (  # type: ignore
        QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
        QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
        QScrollArea, QFrame,
    )
    from PyQt6.QtCore import Qt  # type: ignore
    from PyQt6.QtGui import QFont  # type: ignore
except ImportError:
    # Fallback to PyQt5 in case of older Anki version.
    try:
        from PyQt5.QtWidgets import (  # type: ignore
            QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
            QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
            QScrollArea, QFrame,
        )
        from PyQt5.QtCore import Qt  # type: ignore
        from PyQt5.QtGui import QFont  # type: ignore
    except ImportError:
        raise

try:
    from ..logger import get_logger
except ImportError:
    from logger import get_logger  # type: ignore

log = get_logger("preview")


class PreviewDialog(QDialog):
    """
    Editable card preview dialog shown before a note is committed to Anki.

    After exec(), call get_card_data() to retrieve the (possibly edited) data.
    """

    # Re-export for use in bridge.py without importing QDialog there.
    Accepted = QDialog.DialogCode.Accepted if hasattr(QDialog, "DialogCode") else QDialog.Accepted
    Rejected = QDialog.DialogCode.Rejected if hasattr(QDialog, "DialogCode") else QDialog.Rejected

    def __init__(self, card_data: dict, parent: QWidget | None = None) -> None:
        """
        Initialise the dialog and populate all fields from card_data.

        Args:
            card_data: Dict from pending_card.json.
            parent:    Parent widget (Anki's mw).
        """
        log.debug("PreviewDialog initialised for word='%s'", card_data.get("word"))

        super().__init__(parent)
        self._original_card_data = dict(card_data)

        self.setWindowTitle("AJS — Card Preview")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)

        self._build_ui(card_data)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self, card_data: dict) -> None:
        """Build and populate all widgets."""
        log.debug("Building preview dialog UI")

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)
        root_layout.setContentsMargins(16, 16, 16, 12)

        # ── Title label ──
        title = QLabel("Review and edit the card before adding it to Anki:")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        root_layout.addWidget(title)

        # ── Scrollable form area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        # ── Editable fields ──
        self._word_edit = QLineEdit(card_data.get("word", ""))
        self._word_edit.setPlaceholderText("Kanji / kana form")
        form.addRow("Word:", self._word_edit)

        self._reading_edit = QLineEdit(card_data.get("reading", ""))
        self._reading_edit.setPlaceholderText("Hiragana reading")
        form.addRow("Reading:", self._reading_edit)

        self._romaji_edit = QLineEdit(card_data.get("romaji", ""))
        self._romaji_edit.setPlaceholderText("Romaji pronunciation (e.g. ii to omou)")
        form.addRow("Romaji:", self._romaji_edit)

        self._pos_edit = QLineEdit(card_data.get("part_of_speech", ""))
        self._pos_edit.setPlaceholderText("e.g. noun, verb, い-adjective")
        form.addRow("Part of speech:", self._pos_edit)

        self._definition_edit = QPlainTextEdit(card_data.get("definition_en", ""))
        self._definition_edit.setFixedHeight(72)
        self._definition_edit.setPlaceholderText("English definition")
        form.addRow("Definition (EN):", self._definition_edit)

        self._sentence_edit = QPlainTextEdit(card_data.get("example_sentence", ""))
        self._sentence_edit.setFixedHeight(72)
        self._sentence_edit.setPlaceholderText("Japanese example sentence")
        form.addRow("Example sentence:", self._sentence_edit)

        # ── Read-only display fields ──
        audio_path = card_data.get("audio_path", "")
        audio_display = Path(audio_path).name if audio_path else "(none)"
        audio_label = QLabel(audio_display)
        audio_label.setStyleSheet("color: #666;")
        audio_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Audio file:", audio_label)

        source_url = card_data.get("source_url", "")
        url_label = QLabel(source_url[:80] + ("…" if len(source_url) > 80 else ""))
        url_label.setStyleSheet("color: #666; font-size: 11px;")
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Source URL:", url_label)

        scroll.setWidget(form_widget)
        root_layout.addWidget(scroll, stretch=1)

        # ── Separator ──
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        root_layout.addWidget(separator)

        # ── Button row ──
        btn_box = QDialogButtonBox()

        add_btn = QPushButton("Add Card")
        add_btn.setDefault(True)
        add_btn.setStyleSheet(
            "QPushButton { background: #0077cc; color: white; padding: 6px 18px; "
            "border-radius: 4px; font-weight: bold; } "
            "QPushButton:hover { background: #005fa3; }"
        )
        btn_box.addButton(add_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        skip_btn = QPushButton("Skip")
        skip_btn.setStyleSheet(
            "QPushButton { padding: 6px 14px; border-radius: 4px; } "
            "QPushButton:hover { background: #eee; }"
        )
        btn_box.addButton(skip_btn, QDialogButtonBox.ButtonRole.RejectRole)

        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self._on_skip)

        root_layout.addWidget(btn_box)

        log.debug("Preview dialog UI built")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """User clicked 'Add Card' — validate and accept."""
        log.info("User clicked Add Card")
        word = self._word_edit.text().strip()
        if not word:
            from aqt.utils import showWarning  # type: ignore
            showWarning("Word field cannot be empty. Please enter the word.")
            return
        self.accept()

    def _on_skip(self) -> None:
        """User clicked 'Skip' — reject the dialog."""
        log.info("User clicked Skip")
        self.reject()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_card_data(self) -> dict:
        """
        Return the card data dict with any edits the user made in the dialog.

        Merges the original card_data (to preserve fields not shown in the form,
        e.g. audio_path, source_url, created_at) with the edited values.

        Returns:
            dict with all card fields, incorporating user edits.
        """
        log.debug("Collecting edited card data from dialog")

        edited = dict(self._original_card_data)
        edited["word"]             = self._word_edit.text().strip()
        edited["reading"]          = self._reading_edit.text().strip()
        edited["romaji"]           = self._romaji_edit.text().strip()
        edited["part_of_speech"]   = self._pos_edit.text().strip()
        edited["definition_en"]    = self._definition_edit.toPlainText().strip()
        edited["example_sentence"] = self._sentence_edit.toPlainText().strip()

        log.info("Edited card data: word='%s' reading='%s'", edited["word"], edited["reading"])
        return edited
