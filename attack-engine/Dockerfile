FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY runner.py traffic_generator.py common.py ./

RUN adduser --disabled-password --gecos "" --uid 10001 pantheon
USER 10001:10001

CMD ["python", "runner.py"]
