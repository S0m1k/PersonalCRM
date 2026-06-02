FROM python:3.12-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Зависимости устанавливаем отдельным слоем — кэшируется при неизменном requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходники
COPY . .

# Порт, на котором слушает uvicorn
EXPOSE 8000

# Запуск. В продакшне добавьте --workers N (N = число CPU * 2 + 1)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
