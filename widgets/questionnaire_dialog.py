from textual.screen import ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Label, RadioSet, RadioButton, Input, Button
from textual.app import ComposeResult


class QuestionnaireDialog(ModalScreen):
    """Модальный экран с опросником."""
    
    CSS = """
    QuestionnaireDialog {
        align: center middle;
    }
    #dialog-container {
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    #dialog-question {
        text-align: center;
        margin-bottom: 1;
    }
    #dialog-content {
        height: auto;
        margin-bottom: 1;
    }
    #dialog-buttons {
        height: auto;
        align: center middle;
    }
    """

    def __init__(self, questions: list[dict], **kwargs):
        self.questions = questions
        self.current_q = 0
        self.answers = {}
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Container(id="dialog-container"):
            yield Label(id="dialog-question")
            self.content_container = Container(id="dialog-content")
            yield self.content_container
            with Horizontal(id="dialog-buttons"):
                yield Button("Назад", id="btn-back", variant="primary")
                yield Button("Далее", id="btn-next", variant="success")

    def on_mount(self) -> None:
        self._load_question()

    def _load_question(self) -> None:
        question_label = self.query_one("#dialog-question", Label)
        question_label.update(self.questions[self.current_q]["question"])
        
        self.content_container.remove_children()
        
        q = self.questions[self.current_q]
        if "options" in q:
            radios = [RadioButton(opt) for opt in q["options"]]
            self.radio_set = RadioSet(*radios)
            self.content_container.mount(self.radio_set)
        else:
            self.input_widget = Input(placeholder="Ваш ответ...")
            self.content_container.mount(self.input_widget)

    def _save_current_answer(self) -> None:
        q = self.questions[self.current_q]
        if "options" in q:
            selected = self.radio_set.pressed_index
            self.answers[self.current_q] = selected
        else:
            self.answers[self.current_q] = self.input_widget.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        
        if button_id == "btn-next":
            self._save_current_answer()
            if self.current_q < len(self.questions) - 1:
                self.current_q += 1
                self._load_question()
            else:
                self.dismiss(self.answers)
        elif button_id == "btn-back":
            if self.current_q > 0:
                self.current_q -= 1
                self._load_question()

