FROM docker.io/python:3-slim

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY entrypoint.sh .
COPY app /app

EXPOSE 8000/tcp

USER 1001

ENTRYPOINT ["/entrypoint.sh"]
