FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir docker
COPY logship.py .
CMD ["python", "-u", "logship.py"]
