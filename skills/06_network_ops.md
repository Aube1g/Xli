# Network Operations

## Проверка соединения
<run>ping -c 4 google.com</run>

## DNS запрос
<run>nslookup google.com</run>
<run>dig google.com</run>

## HTTP запрос (curl)
<run>curl -s https://api.example.com</run>

## HTTP запрос с заголовками
<run>curl -H "Content-Type: application/json" https://api.example.com</run>

## POST запрос
<run>curl -X POST -d '{"key":"value"}' https://api.example.com</run>

## Скачать файл
<run>curl -O https://example.com/file.zip</run>

## Скачать с прогрессом
<run>curl -L -O --progress-bar https://example.com/file.zip</run>

## Wget скачать
<run>wget https://example.com/file.zip</run>

## IP адрес
<run>curl ifconfig.me</run>

## Что слушает порты
<run>netstat -tlnp</run> (Linux)
<run>ss -tlnp</run>

## Порт открыт?
<run>nc -zv localhost 8000</run>

## Сканирование портов
<run>nmap -p 1-1000 localhost</run> (если установлен)

## SSH подключение
<run>ssh user@host</run>

## Копирование через SSH
<run>scp file.txt user@host:/path/</run>
