# Termux Specific Operations

## Запросить разрешение на хранение
<run>termux-setup-storage</run>

## Список датчиков
<run>termux-sensor -l</run>

## Данные датчиков
<run>termux-sensor -s "sensor_name"</run>

## Батарея
<run>termux-battery-status</run>

## Уведомление
<run>termux-notification --title "Title" --content "Message"</run>

## Тост
<run>termux-toast "Message"</run>

## Вибро
<run>termux-vibrate -d 1000</run>

## WiFi список
<run>termux-wifi-scaninfo</run>

## Выключить дисплей
<run>termux-display -t 0</run>

## Включить дисплей
<run>termux-display -t -1</run>

## TTS (озвучка)
<run>termux-tts-speak "Hello"</run>

## Контакты
<run>termux-contact-list</run>

## SMS отправить
<run>termux-sms-send -n +1234567890 "message"</run>

## Камера (фото)
<run>termux-camera-photo photo.jpg</run>

## Открыть ссылку
<run>termux-open-url https://google.com</run>

## Пакеты Termux
Поиск: <run>pkg search keyword</run>
Установка: <run>pkg install package</run>
Обновить всё: <run>pkg update && pkg upgrade -y</run>
Список: <run>pkg list-all</run>

## Проекты Termux
Путь к хранилищу: <run>echo $HOME/storage</run>
Внутренняя память: <run>ls /sdcard</run>
