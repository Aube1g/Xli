# Git Operations

## Статус
<run>git status</run>

## Добавить файлы
<run>git add .</run>
<run>git add file.py</run>

## Коммит
<run>git commit -m "message"</run>

## Коммит с добавлением всех
<run>git commit -am "message"</run>

## Push
<run>git push origin main</run>

## Pull
<run>git pull origin main</run>

## Логи (последние 10)
<run>git log --oneline -10</run>

## Логи с графиком
<run>git log --graph --oneline -10</run>

## Ветки
<run>git branch -a</run>

## Создать ветку
<run>git checkout -b feature/name</run>

## Переключиться на ветку
<run>git checkout main</run>

## Удалить ветку локально
<run>git branch -d branch_name</run>

## Клонировать репозиторий
<run>git clone https://github.com/user/repo.git</run>

## Показать изменения
<run>git diff</run>

## Откатить незакоммиченные изменения
<run>git checkout -- file.py</run>

## Откатить коммит (мягко)
<run>git reset --soft HEAD~1</run>

## Откатить коммит (жёстко)
<run>git reset --hard HEAD~1</run>
