# Python Operations

## Запустить скрипт
<run>python3 script.py</run>

## Запустить с аргументами
<run>python3 script.py --arg value</run>

## Проверить синтаксис
<run>python3 -m py_compile script.py</run>

## Запустить модуль
<run>python3 -m http.server 8000</run>

## Установить пакет
<run>pip install package</run>

## Установить конкретную версию
<run>pip install package==1.2.3</run>

## Установить из requirements.txt
<run>pip install -r requirements.txt</run>

## Создать requirements.txt
<run>pip freeze > requirements.txt</run>

## Удалить пакет
<run>pip uninstall package -y</run>

## Список установленных пакетов
<run>pip list</run>

## Проверить устаревшие пакеты
<run>pip list --outdated</run>

## Создать venv
<run>python3 -m venv venv</run>

## Активировать venv (Linux/Mac)
<run>source venv/bin/activate</run>

## Активировать venv (Windows)
<run>venv\\Scripts\\activate</run>

## Установка в venv
<run>venv/bin/pip install package</run>

## Запуск в venv
<run>venv/bin/python script.py</run>

## Форматирование (black)
<run>black script.py</run>

## Проверка стиля (flake8)
<run>flake8 script.py</run>

## Тестирование (pytest)
<run>pytest tests/</run>
