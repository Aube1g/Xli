# System Operations

## Информация о системе
<run>uname -a</run>

## Диск
<run>df -h</run>

## Память
<run>free -h</run>

## Загрузка системы
<run>uptime</run>

## Кто в системе
<run>whoami</run>
<run>who</run>

## Переменные окружения
<run>env</run>

## Текущая директория
<run>pwd</run>

## Список пользователей
<run>ls /home/</run> (Linux)
<run>ls /data/data/com.termux/files/home/</run> (Termux)

## Дата и время
<run>date</run>

## Календарь
<run>cal</run>

## Поиск файла
<run>find . -name "*.py" -type f</run>

## Поиск по содержимому (быстро)
<run>grep -r "pattern" . --color</run>

## Поиск с ripgrep (если установлен)
<run>rg "pattern"</run>
