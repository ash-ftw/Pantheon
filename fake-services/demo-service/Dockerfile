FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app
COPY server.py .

RUN adduser --disabled-password --gecos "" --uid 10001 pantheon
USER 10001:10001

EXPOSE 8080
CMD ["python", "server.py"]
