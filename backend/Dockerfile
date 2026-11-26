FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_demo --levels-only && gunicorn config.wsgi:application -b 0.0.0.0:8000 --workers 3"]
