import json
import re
from .mistral_client import call_mistral_agent

async def generate_questions(task: str, agent_id: str) -> list:
    """Генерирует уточняющие вопросы через AI"""
    
    prompt = f"""Ты - AI ассистент. Пользователь дал задачу: "{task}"

Задача недостаточно конкретна. Сгенерируй 2-4 уточняющих вопроса, которые помогут понять, что именно нужно сделать.

Правила:
- Вопросы должны быть краткими и конкретными
- Предлагай варианты ответов для выбора (2-4 варианта)
- Вопросы должны касаться только НЕЯСНЫХ аспектов задачи

Формат ответа (строго JSON):
{{
    "questions": [
        {{
            "question": "текст вопроса",
            "options": ["вариант1", "вариант2", "вариант3"]
        }}
    ]
}}

Не добавляй пояснений, только JSON."""

    response = await call_mistral_agent(agent_id, [{"role": "user", "content": prompt}], temperature=0.7)
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("questions", [])
    except Exception as e:
        print(f"Ошибка парсинга вопросов: {e}")
    
    return []

async def clarify_task_with_dialog(original_task: str, agent_id: str, app) -> tuple:
    """
    Уточняет задачу через диалоговое окно
    Возвращает (уточнённая_задача, была_ли_показана_диалог)
    """
    # Если задача уже детальная — не спрашиваем
    if len(original_task.split()) > 25 or len(original_task) > 150:
        return original_task, False
    
    questions = await generate_questions(original_task, agent_id)
    
    if not questions:
        return original_task, False
    
    # Показываем диалог
    from widgets.questionnaire_dialog import QuestionnaireDialog
    answers = await app.push_screen_wait(QuestionnaireDialog(questions, None))
    
    if not answers:
        return original_task, True
    
    # Формируем уточнённую задачу
    enhanced = original_task + "\n\n**Уточнения от пользователя:**\n"
    for q, a in answers.items():
        enhanced += f"- {q} → {a}\n"
    
    return enhanced, True
