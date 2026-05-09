# File Operations

## Создать файл
<run>echo "content" > file.txt</run>

## Создать многострочный файл
<run>cat > script.py << 'EOF'
def hello():
    print("Hello")
EOF</run>

## Прочитать файл
<run>cat file.txt</run>

## Посмотреть первые строки
<run>head -20 file.txt</run>

## Посмотреть последние строки
<run>tail -20 file.txt</run>

## Посчитать строки
<run>wc -l file.txt</run>

## Поиск в файле
<run>grep "pattern" file.txt</run>

## Замена в файле (sed)
<run>sed -i 's/old/new/g' file.txt</run>

## Копировать
<run>cp source.txt dest.txt</run>

## Переместить/переименовать
<run>mv old.txt new.txt</run>

## Удалить
<run>rm file.txt</run>

## Удалить папку с содержимым
<run>rm -rf folder/</run>

## Создать папку
<run>mkdir -p path/to/folder</run>

## Древо папок
<run>find . -type d | head -30</run>

## Размер файла
<run>du -sh file.txt</run>

## Символическая ссылка
<run>ln -s /target link</run>
