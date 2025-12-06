import sys
import pygame
from PySide6.QtCore import Signal, Slot, Qt, QThread, QPoint
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel
import difflib

# Autocomplete Data
# Load word list
try:
    with open("words.txt", "r", encoding="utf-8") as f:
        WORDS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    print("Warning: 'words.txt' not found. Autocomplete will be limited to abbreviations.")
    WORDS = []

ABBREVIATIONS = {
    "abt": "about", "ad": "advertisement", "asap": "as soon as possible",
    "atm": "at the moment", "bc": "because", "bday": "birthday",
    "bf": "boyfriend", "bff": "best friends forever", "brb": "be right back",
    "btw": "by the way", "cm": "centimeter", "cya": "see you",
    "DIY": "do it yourself", "doc": "doctor", "e.g.": "for example",
    "etc": "and so on", "fyi": "for your information", "idk": "I don't know",
    "imo": "in my opinion", "jk": "just kidding", "lmk": "let me know",
    "lol": "laugh out loud", "np": "no problem", "omg": "oh my god",
    "pls": "please", "tmrw": "tomorrow", "u": "you", "ur": "your",
}


def generate_suggestions(current_text, limit=4):
    if not current_text or current_text.strip() == "":
        return []

    suggestions = []
    last_word = current_text.split()[-1].lower() if current_text.split() else ""

    if not last_word:
        return []

    if last_word in ABBREVIATIONS:
        suggestions.append(ABBREVIATIONS[last_word] + " ")

    for word in WORDS:
        if word.lower().startswith(last_word) and (word + " ") not in suggestions:
            suggestions.append(word + " ")
        if len(suggestions) >= limit:
            break

    if not suggestions and WORDS:
        close_matches = difflib.get_close_matches(last_word, WORDS, n=limit, cutoff=0.6)
        clean_matches = [match + " " for match in close_matches if match.lower() != last_word]
        suggestions.extend(clean_matches)

    return suggestions[:limit]


# ------------------ Controller Worker ------------------ #
class ControllerWorker(QThread):
    move_left = Signal()
    move_right = Signal()
    direct_row_select = Signal(int)
    select_letter = Signal()
    delete_char = Signal()
    toggle_caps = Signal()
    insert_space = Signal()

    # Autocomplete signals
    toggle_autocomplete = Signal()
    move_suggestion_left = Signal()
    move_suggestion_right = Signal()
    select_suggestion = Signal()

    autocomplete_active = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.inside_row = False
        self.delete_held = False
        self._running = True

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        pygame.init()
        pygame.joystick.init()

        controller = None
        if pygame.joystick.get_count() > 0:
            controller = pygame.joystick.Joystick(0)
            controller.init()
            print("-" * 30)
            print(f"Controller detected: {controller.get_name()}")
            print("-" * 30)
        else:
            print("No controller detected. Controller inputs will be inactive.")
            pygame.quit()
            return

        while self._running:
            pygame.time.wait(10)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    break

                if event.type == pygame.JOYBUTTONDOWN:
                    # Button mappings
                    # 0=B, 1=A, 2=X, 3=Y, 4=LB, 6=RB, 7=LT, 8=RT, 9=Minus, 10=Plus, 11=Home, 12=Screenshot

                    # A, B, X, Y open rows when in row select mode

                    # Opens select mode, or returns user to row if in autocomplete
                    if event.button == 1:  # A Button
                        if self.autocomplete_active:
                            self.toggle_autocomplete.emit()  # Toggle OFF
                            continue
                        elif self.inside_row:
                            # Exit row mode
                            self.inside_row = False
                            self.direct_row_select.emit(-1)
                        else:
                            # Direct Row Select: A opens Row 2
                            self.direct_row_select.emit(2)
                        continue

                    # Selects a row, and when in a row move
                    if event.button == 3:  # Y Button
                        if self.autocomplete_active:
                            self.move_suggestion_left.emit()
                        elif self.inside_row:
                            self.move_left.emit()
                        else:
                            self.direct_row_select.emit(1)

                    # Selects a row, and when in a row move
                    elif event.button == 0:  # B Button
                        if self.autocomplete_active:
                            self.move_suggestion_right.emit()
                        elif self.inside_row:
                            self.move_right.emit()
                        else:
                            self.direct_row_select.emit(3)

                    # Adds words/letters to the text
                    elif event.button == 8:  # RT / Select Button
                        if self.autocomplete_active:
                            self.select_suggestion.emit()  # Selects the entire suggestion word
                        elif self.inside_row:
                            self.select_letter.emit()  # Adds the current letter

                    elif event.button == 2:  # X Button
                        if self.inside_row:
                            self.toggle_caps.emit()
                        else:
                            self.direct_row_select.emit(0)

                    # Delete the current letter
                    elif event.button == 11: # Home
                        self.delete_char.emit()

                    # Insert a space
                    elif event.button == 10: # Plus
                        self.insert_space.emit()

                    # Toggle autocomplete
                    elif event.button == 6: # Right bumper
                        self.toggle_autocomplete.emit()

        pygame.quit()

class OnScreenKeyboard(QMainWindow):
    def __init__(self):
        super().__init__()

        # Window setup
        self.setWindowTitle("Controller Keyboard Overlay")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(900, 600)

        # State
        self.inside_row = False
        self.is_caps_locked = False

        # New State for restoring position after autocomplete
        self.prev_inside_row = False
        self.prev_sel_row = 0
        self.prev_sel_index = 0

        # Keyboard data
        self.base_rows = [
            list("EICVJWH"),
            list("ORYQBU"),
            list("TNMKZGD"),
            list("ASFXPL"),
        ]
        self.rows = self._regenerate_keyboard_rows()
        self.sel_row = 0
        self.sel_index = 0
        self.row_labels = []

        # UI Setup
        container = QWidget()
        container.setObjectName("Container")
        container.setStyleSheet("""
            QWidget#Container {
                background-color: rgba(20, 20, 30, 230); 
                border: 2px solid #0078d7;
                border-radius: 15px;
            }
            QLabel { color: #eeeeee; font-weight: bold; }
        """)
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. Output Label
        self.output = QLabel("Typing...")
        self.output.setAlignment(Qt.AlignCenter)
        self.output.setFixedHeight(60)
        self.output.setStyleSheet('font: 24pt "Segoe UI"; background-color: rgba(0,0,0,100); border-radius: 8px;')
        layout.addWidget(self.output, 0)

        # 2. Autocomplete Suggestion Label
        self.suggestion_label = QLabel("")
        self.suggestion_label.setAlignment(Qt.AlignCenter)
        self.suggestion_label.setStyleSheet('font: 16pt "Segoe UI"; min-height: 40px;')
        layout.addWidget(self.suggestion_label, 0)

        # Diamond Container for Rows
        diamond_container = QWidget()
        diamond_container.setFixedSize(800, 450)
        diamond_container.setObjectName("DiamondContainer")
        layout.addWidget(diamond_container, 20, alignment=Qt.AlignCenter)

        positions = [QPoint(400, 30), QPoint(150, 225), QPoint(650, 225), QPoint(400, 420)]

        for index, row in enumerate(self.rows):
            lbl = QLabel(" ".join(row), diamond_container)
            lbl.setStyleSheet('font: 30pt "Segoe UI";')
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(400)
            lbl.setFixedHeight(50)

            x_pos = positions[index].x() - (lbl.width() // 2)
            y_pos = positions[index].y() - (lbl.height() // 2)

            lbl.move(x_pos, y_pos)
            self.row_labels.append(lbl)

        # Worker
        self.worker = ControllerWorker()
        self.worker.move_left.connect(self.move_left)
        self.worker.move_right.connect(self.move_right)
        self.worker.direct_row_select.connect(self.set_row_and_enter_mode)
        self.worker.select_letter.connect(self.add_or_select_function)
        self.worker.delete_char.connect(self.backspace)
        self.worker.toggle_caps.connect(self.toggle_caps_lock)
        self.worker.insert_space.connect(self.add_space)

        # Autocomplete connections
        self.worker.toggle_autocomplete.connect(self.toggle_autocomplete)
        self.worker.move_suggestion_left.connect(self.prev_suggestion)
        self.worker.move_suggestion_right.connect(self.next_suggestion)
        self.worker.select_suggestion.connect(self.select_suggestion)

        self.worker.start()
        app.aboutToQuit.connect(self.worker.stop)

        # Hint
        layout.addStretch(1)
        hint = QLabel(
            "KEYBOARD: [A/B/X/Y]: Row Select | [Y/B]: Move Cursor | [RT]: Select Letter | [RB]: Autocomplete | AUTOSUGGEST: [A]: Exit | [Y/B]: Change Word | [RT]: Select Word"
        )
        hint.setStyleSheet("color: #aaa; font-size: 10pt;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint, 0)

        self.update_highlight()

        # Autocomplete state
        self.autocomplete_active = False
        self.suggestions = []
        self.suggestion_index = 0

    # Keyboard Logic
    def _regenerate_keyboard_rows(self):
        new_rows = []
        for row in self.base_rows:
            new_row = []
            for item in row:
                if len(item) == 1:
                    new_row.append(item.upper() if self.is_caps_locked else item.lower())
                else:
                    new_row.append(item)
            new_rows.append(new_row)
        return new_rows

    @Slot()
    def toggle_caps_lock(self):
        self.is_caps_locked = not self.is_caps_locked
        self.rows = self._regenerate_keyboard_rows()
        self.update_highlight()

    @Slot(int)
    def set_row_and_enter_mode(self, row_index):
        if row_index == -1:
            self.inside_row = False
            self.worker.inside_row = False
            self.update_highlight()
            return

        self.sel_row = row_index
        self.sel_index = 0
        self.inside_row = True
        self.worker.inside_row = True
        self.update_highlight()

    @Slot()
    def move_left(self):
        if not self.inside_row: return
        row_length = len(self.rows[self.sel_row])
        self.sel_index = (self.sel_index - 1) % row_length
        self.update_highlight()

    @Slot()
    def move_right(self):
        if not self.inside_row: return
        row_length = len(self.rows[self.sel_row])
        self.sel_index = (self.sel_index + 1) % row_length
        self.update_highlight()

    @Slot()
    def add_or_select_function(self):
        if not self.inside_row: return
        current_text = self.output.text()
        if current_text == "Typing...": current_text = ""
        item = self.rows[self.sel_row][self.sel_index]
        self.output.setText(current_text + item)

    @Slot()
    def add_space(self):
        current_text = self.output.text()
        if current_text == "Typing...": current_text = ""
        self.output.setText(current_text + " ")

    @Slot()
    def backspace(self):
        current = self.output.text()
        if current and current != "Typing...":
            self.output.setText(current[:-1])

    # ------------------ Autocomplete Slots ------------------ #
    @Slot()
    def toggle_autocomplete(self):
        self.autocomplete_active = not self.autocomplete_active
        self.worker.autocomplete_active = self.autocomplete_active

        if self.autocomplete_active:
            # When turning ON, save current position
            self.prev_inside_row = self.inside_row
            self.prev_sel_row = self.sel_row
            self.prev_sel_index = self.sel_index

            # Optionally, disable row display while in autocomplete mode
            self.inside_row = False

            self.update_suggestions()
        else:
            # When turning OFF (by A or RB), restore previous position
            self.inside_row = self.prev_inside_row
            self.sel_row = self.prev_sel_row
            self.sel_index = self.prev_sel_index
            self.worker.inside_row = self.prev_inside_row  # Restore worker's state too

            self.suggestion_label.setText("")
            self.update_highlight()

    def update_suggestions(self):
        text = self.output.text()
        if text == "Typing...": text = ""
        self.suggestions = generate_suggestions(text)
        self.suggestion_index = 0
        self.display_suggestions()

    def display_suggestions(self):
        if self.suggestions and self.autocomplete_active:
            display_text = ""
            for i, s in enumerate(self.suggestions):
                if i == self.suggestion_index:
                    display_text += f"<span style='background-color: #0078d7; color: white; padding: 2px 10px; border-radius: 5px;'>{s.strip()}</span> "
                else:
                    display_text += f"<span style='color: #ccc; padding: 2px 10px;'>{s.strip()}</span> "
            self.suggestion_label.setText(display_text)
        elif self.autocomplete_active:
            self.suggestion_label.setText("<span style='color: #ccc;'>No suggestions</span>")
        else:
            self.suggestion_label.setText("")

    @Slot()
    def prev_suggestion(self):
        if not self.suggestions or not self.autocomplete_active: return
        self.suggestion_index = (self.suggestion_index - 1) % len(self.suggestions)
        self.display_suggestions()

    @Slot()
    def next_suggestion(self):
        if not self.suggestions or not self.autocomplete_active: return
        self.suggestion_index = (self.suggestion_index + 1) % len(self.suggestions)
        self.display_suggestions()

    @Slot()
    def select_suggestion(self):
        if not self.suggestions or not self.autocomplete_active: return

        text = self.output.text()
        if text == "Typing...": text = ""

        suggestion_text = self.suggestions[self.suggestion_index]

        words = text.split()
        if words:
            new_text = " ".join(words[:-1]) + " " + suggestion_text
        else:
            new_text = suggestion_text

        self.output.setText(new_text.strip() + " ")

        # Turn off autocomplete after selection
        self.toggle_autocomplete()

    # UI Update
    def update_highlight(self):
        for r, label in enumerate(self.row_labels):
            text = ""
            for i, item in enumerate(self.rows[r]):
                base_item = self.base_rows[r][i]
                is_function_key = len(base_item) > 1
                display_item = item if not is_function_key else f"<{item}>"

                if r == self.sel_row and self.inside_row:
                    if i == self.sel_index:
                        text += f"<span style='background-color: #0078d7; color: white; padding: 0 10px; border-radius: 5px;'>{display_item}</span> "
                    else:
                        text += f"<span style='color: white; padding: 0 10px;'>{display_item}</span> "
                else:
                    text += f"<span style='color: #666; padding: 0 10px;'>{display_item}</span> "
            label.setText(text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OnScreenKeyboard()
    win.show()
    sys.exit(app.exec())