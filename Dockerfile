# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл с зависимостями в рабочую директорию
COPY requirements.txt .

# Устанавливаем зависимости
# --no-cache-dir - не сохраняем кэш, чтобы уменьшить размер образа
# build-essential - необходим для компиляции некоторых зависимостей, например, numpy
RUN apt-get update && apt-get install -y build-essential && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y build-essential && apt-get clean

# Копируем остальные файлы проекта в рабочую директорию
COPY . .

# Указываем команду для запуска приложения
CMD ["python3", "main.py"]
