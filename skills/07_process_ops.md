# Process Operations

## Список процессов
<run>ps aux</run>

## Поиск процесса
<run>ps aux | grep python</run>

## Поиск по PID
<run>ps -p 1234</run>

## Завершить процесс по PID
<run>kill 1234</run>

## Принудительно завершить
<run>kill -9 1234</run>

## Завершить по имени
<run>pkill python</run>

## Завершить все процессы
<run>killall python</run>

## Запустить в фоне
<run>python script.py &</run>

## Фоновые процессы
<run>jobs</run>

## Вернуть в foreground
<run>fg %1</run>

## Топ процессов
<run>top -n 1 -b</run>

## Использование CPU/памяти
<run>htop</run> (если установлен)

## Проверить работает ли процесс
<run>pgrep -x python3</run>

## Запуск с ограничением времени
<run>timeout 10s python script.py</run>
