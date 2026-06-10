FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py config.py processor.py workbook_storage.py logging_config.py ./
COPY static ./static
COPY templates ./templates

ENV PORT=8501 \
    WORKBOOK_STORAGE=s3 \
    LOG_LEVEL=INFO

EXPOSE 8501

CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
