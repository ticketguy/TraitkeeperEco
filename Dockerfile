FROM python:3.12-slim as builder

RUN apt-get update && apt-get install -y \
    gcc g++ postgresql-client libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel
RUN pip install poetry==2.2.1

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-ansi --no-root

FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    postgresql-client libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN mkdir -p staticfiles media logs

EXPOSE 8000

CMD ["gunicorn", "traitkeeper.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
