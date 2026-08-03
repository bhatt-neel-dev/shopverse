FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir locust
COPY locustfile.py .
EXPOSE 8089
CMD ["sh", "-c", "locust -f locustfile.py --host ${GATEWAY_URL:-http://gateway:8080} --web-port 8089 --autostart -u ${BASELINE_USERS:-5} -r 1"]
