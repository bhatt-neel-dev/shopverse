FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends snmp \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY trapgen.py .
EXPOSE 7070
CMD ["python", "trapgen.py"]
