FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir pymysql pymongo cryptography
COPY seed.py .
CMD ["python", "seed.py"]
