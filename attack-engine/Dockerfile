FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY runner.py traffic_generator.py common.py ./

CMD ["python", "runner.py"]
