FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt
RUN useradd --create-home appuser && mkdir /app/data && chown appuser:appuser /app/data
COPY *.py ./
USER appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "240", "app:app"]
