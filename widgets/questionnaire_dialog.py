from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Button, Input, RadioButton, RadioSet, Label
from textual.screen import ModalScreen

class QuestionnaireDialog(ModalScreen):
    """Диалоговое окно для опросника с вопросами"""

    def __init__(self, questions: list, callback=None):
        super().__init__()
        self.questions = questions
        self.callback = callback
        self.current_q = 0
        self.answers = {}
        self.radio_set = None
        self.input_field = None

    def compose(self) -> ComposeResult:
        """Создаёт интерфейс диалога"""
        with Container(id="dialog-container"):
            yield Label(f"📋 Вопрос {self.current_q + 1} из {len(self.questions)}", id="dialog-title")
            yield Label(self.questions[self.current_q]["question"], id="dialog-question")
            
            # Содержимое для текущего вопроса
            yield self._build_current_widget()
            
            # Кнопки
            with Horizontal(id="dialog-buttons"):
                if self.current_q > 0:
                    yield Button("◀ Назад", id="prev-btn", variant="default")
                yield Button("Далее ▶", id="next-btn", variant="primary")

    def _build_current_widget(self):
        """Создаёт виджет для текущего вопроса"""
        q = self.questions[self.current_q]
        
        if q.get("options"):
            # Для вариантов ответа используем RadioSet
            self.radio_set = RadioSet()
            for opt in q["options"]:
                self.radio_set.mount(RadioButton(opt))
            return self.radio_set
        else:
            # Для свободного ответа используем Input
            self.input_field = Input(placeholder="Введите ответ...")
            return self.input_field

    def on_button_pressed(self, event: Button.Pressed):
        """Обработка нажатия кнопок"""
        if event.button.id == "next-btn":
            self._save_current_answer()
            if self.current_q + 1 < len(self.questions):
                self.current_q += 1
                self._refresh_dialog()
            else:
                self.dismiss(self.answers)
        elif event.button.id == "prev-btn":
            self.current_q -= 1
            self._refresh_dialog()

    def _save_current_answer(self):
        """Сохраняет ответ на текущий вопрос"""
        q = self.questions[self.current_q]
        
        if q.get("options") and self.radio_set:
            # Находим выбранный вариант
            for rb in self.radio_set.query(RadioButton):
                if rb.value:
                    self.answers[q["question"]] = rb.label.plain
                    break
        elif self.input_field and self.input_field.value:
            self.answers[q["question"]] = self.input_field.value

    def _refresh_dialog(self):
        """Обновляет диалог для следующего вопроса"""
        q = self.questions[self.current_q]
        
        # Обновляем заголовки
        self.query_one("#dialog-title").update(f"📋 Вопрос {self.current_q + 1} из {len(self.questions)}")
        self.query_one("#dialog-question").update(q["question"])
        
        # Удаляем старый виджет
        if self.radio_set:
            self.radio_set.remove()
            self.radio_set = None
        if self.input_field:
            self.input_field.remove()
            self.input_field = None
        
        # Добавляем новый виджет
        new_widget = self._build_current_widget()
        # Вставляем перед кнопками
        buttons = self.query_one("#dialog-buttons")
        self.mount(new_widget, before=buttons)
        
        # Обновляем кнопки
        buttons.remove_children()
        if self.current_q > 0:
            buttons.mount(Button("◀ Назад", id="prev-btn", variant="default"))
        buttons.mount(Button("Далее ▶", id="next-btn", variant="primary"))

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)
