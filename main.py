import sys
import pygame
from PySide6.QtCore import QObject, Signal, Slot, Qt, QThread, QPoint
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel)


# ------------------ Xbox Controller Worker ------------------ #
class ControllerWorker(QThread):
    # Signals to send to the main UI
    move_left = Signal()
    move_right = Signal()

    # Signal for direct row selection
    direct_row_select = Signal(int)

    select_letter = Signal()
    delete_char = Signal()

    # Signal to toggle Caps Lock
    toggle_caps = Signal()

    # NEW: Signal specifically for adding a space
    insert_space = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.inside_row = False
        self.delete_held = False  # Initialize debounce flag

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
            return

        running = True
        while running:
            pygame.time.wait(10)

            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    # BUTTON MAPPINGS FOR SWITCH PRO CONTROLLER (Common Linux Layout)
                    # 0=B, 1=A, 2=Y, 3=X, 4=L, 5=R, 6=ZL, 7=ZR, 8=Minus, 9=Plus

                    # Row Cursor Movement: Y (3) and B (0)
                    if event.button == 3:  # Y Button
                        if self.inside_row:
                            self.move_left.emit()
                        else:
                            # Direct Row Select: Y opens Row 0 (EICV...)
                            self.direct_row_select.emit(0)

                    if event.button == 0:  # B Button
                        if self.inside_row:
                            self.move_right.emit()
                        else:
                            # Direct Row Select: B opens Row 2 (TNMK...)
                            self.direct_row_select.emit(2)

                    if event.button == 1:  # A Button
                        if self.inside_row:
                            self.inside_row = False
                        else:
                            # Direct Row Select: A opens Row 3 (ASFXPL)
                            self.direct_row_select.emit(3)

                    if event.button == 2:  # X Button
                        if self.inside_row:
                            # Emit signal to toggle Caps Lock
                            self.toggle_caps.emit()
                        else:
                            # Direct Row Select: X opens Row 1 (ORYQ...)
                            self.direct_row_select.emit(1)

                    # Right trigger Button - to select the current letter
                    elif event.button == 8:
                        if self.inside_row:
                            self.select_letter.emit()

                    # UPDATED: Plus/Start Button (9) always inserts a space when in a row
                    elif event.button == 9:  # Plus Button (Start)
                        if self.inside_row:
                            self.insert_space.emit()

            # Digital check for Delete/Backspace (Button 7 is usually ZR - Right Trigger)
            if controller:
                # Check for Right Trigger (usually button 7, but often axis mapping is more reliable for triggers)
                # Sticking to button 7 as per common Switch Pro Linux mapping for this example
                if controller.get_numbuttons() > 7 and controller.get_button(7):
                    # Debounce check to prevent spamming backspace
                    if not self.delete_held:
                        self.delete_char.emit()
                        self.delete_held = True
                else:
                    self.delete_held = False


# ------------------ On-Screen Keyboard ------------------ #
class OnScreenKeyboard(QMainWindow):
    def __init__(self):
        super().__init__()

        # 1. WINDOW SETUP
        self.setWindowTitle("Controller Keyboard Overlay")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(900, 550)

        # STATE
        self.inside_row = False
        self.is_caps_locked = False

        # DATA (All uppercase internally for simplicity in switching)
        self.base_rows = [
            list("EICVJWH"),
            list("ORYQBU"),
            list("TNMKZGD"),
            list("ASFXPL"),
            ["SPACE", "BACK"],
        ]
        self.rows = self._regenerate_keyboard_rows()

        self.sel_row = 0
        self.sel_index = 0
        self.row_labels = []

        # 2. UI SETUP
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

        # Output Label (Fixed size, stretch 0)
        self.output = QLabel("Typing...")
        self.output.setAlignment(Qt.AlignCenter)
        self.output.setFixedHeight(60)
        self.output.setStyleSheet('font: 24pt "Segoe UI"; background-color: rgba(0,0,0,100); border-radius: 8px;')
        layout.addWidget(self.output, 0)  # stretch factor 0

        # Row Container - To apply stretch to all rows evenly
        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(5)  # Add a small gap between rows

        # Build UI Rows
        for index, row in enumerate(self.rows):
            lbl = QLabel(" ".join(row))
            lbl.setStyleSheet('font: 22pt "Segoe UI";')
            lbl.setAlignment(Qt.AlignCenter)
            # Add label to the inner rows layout, giving each one equal stretch
            rows_layout.addWidget(lbl, 1)
            self.row_labels.append(lbl)

        # Add the entire row container to the main layout with a high stretch factor (e.g., 20)
        # This makes the rows dominate the available vertical space.
        layout.addWidget(rows_container, 20)

        # 3. CONTROLLER THREAD SETUP
        self.worker = ControllerWorker()
        self.worker.move_left.connect(self.move_left)
        self.worker.move_right.connect(self.move_right)

        # Connection for direct row selection (X, Y, B, A buttons)
        self.worker.direct_row_select.connect(self.set_row_and_enter_mode)

        self.worker.select_letter.connect(self.add_or_select_function)
        self.worker.delete_char.connect(self.backspace)

        # Connection for Caps Lock
        self.worker.toggle_caps.connect(self.toggle_caps_lock)

        # NEW: Connection for Plus button (always adds space)
        self.worker.insert_space.connect(self.add_space)

        self.worker.start()

        # Instructions
        # Use a small stretch before and a fixed size for the hint
        layout.addStretch(1)
        # UPDATED HINT: Changed [Minus/Plus] to [Minus] Select and [Plus] Space
        hint = QLabel(
            "CONTROLS: [A/B/X/Y]: Direct Row Select | [Y/B]: Move Cursor | [Minus]: Select | [Plus]: Space | [ZR]: Delete | [X]: Toggle CAPS")
        hint.setStyleSheet("color: #aaa; font-size: 10pt;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint, 0)  # stretch factor 0

        self.update_highlight()

    # ------------------ Data and State Logic ------------------ #

    def _regenerate_keyboard_rows(self):
        """ Regenerates the rows based on the current caps lock state. """
        new_rows = []
        for row in self.base_rows:
            new_row = []
            for item in row:
                if len(item) == 1:  # Only change case for single letters
                    new_row.append(item.upper() if self.is_caps_locked else item.lower())
                else:  # Keep SPACE/BACK as is
                    new_row.append(item)
            new_rows.append(new_row)
        return new_rows

    @Slot()
    def toggle_caps_lock(self):
        """ Slot to handle Caps Lock press (X button). """
        self.is_caps_locked = not self.is_caps_locked
        self.rows = self._regenerate_keyboard_rows()
        self.update_highlight()

    # ------------------ Mode and Row Selection Slots ------------------ #
    @Slot(int)
    def set_row_and_enter_mode(self, row_index):
        """ Sets the selected row and automatically enters Letter Select Mode """
        self.sel_row = row_index
        self.sel_index = 0
        self.inside_row = True
        self.worker.inside_row = True  # Sync worker state
        self.update_highlight()

    # ------------------ Navigation Slots ------------------ #
    @Slot()
    def move_left(self):
        if not self.inside_row: return
        self.sel_index = max(0, self.sel_index - 1)
        self.update_highlight()

    @Slot()
    def move_right(self):
        if not self.inside_row: return
        self.sel_index = min(len(self.rows[self.sel_row]) - 1, self.sel_index + 1)
        self.update_highlight()

    @Slot()
    def add_or_select_function(self):
        """ Handles adding a letter, space, or backspace when a key is selected (via Minus/Select button) """

        if not self.inside_row: return

        current_text = self.output.text()
        if current_text == "Typing...": current_text = ""

        item = self.rows[self.sel_row][self.sel_index]

        # NOTE: Only need to check for BACK here, as SPACE is now handled by the Plus button
        if item == "BACK":
            self.backspace()
        elif item == "SPACE":
            # If the user selects the SPACE key via the Minus/Select button, it still works
            self.add_space()
        else:
            # It's a normal letter
            self.output.setText(current_text + item)

    @Slot()
    def add_space(self):
        """ Slot to handle the dedicated Space button (Plus button) """
        current_text = self.output.text()
        if current_text == "Typing...": current_text = ""
        self.output.setText(current_text + " ")

    @Slot()
    def backspace(self):
        """ Used by the Right Trigger (ZR/RT) and the 'BACK' button in the UI """
        current = self.output.text()
        if current and current != "Typing...":
            self.output.setText(current[:-1])

    # ------------------ Visual Update ------------------ #
    def update_highlight(self):
        # Update the UI display rows based on the current self.rows (which reflects caps state)
        for r, label in enumerate(self.row_labels):
            text = ""
            for i, item in enumerate(self.rows[r]):

                # Check if we need to display a special character
                base_item = self.base_rows[r][i]
                display_item = item if len(base_item) == 1 else f"<{item}>"

                if r == self.sel_row and self.inside_row:
                    if i == self.sel_index:
                        # Blue Highlight (Active Selection)
                        text += f"<span style='background-color: #0078d7; color: white; padding: 0 10px;'>{display_item}</span> "
                    else:
                        # Active Row White
                        text += f"<span style='color: white;'>{display_item}</span> "
                else:
                    # Inactive Row Gray
                    text += f"<span style='color: #666;'>{display_item}</span> "
            label.setText(text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OnScreenKeyboard()
    win.show()
    sys.exit(app.exec())