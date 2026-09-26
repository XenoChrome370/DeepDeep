FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEEPDEEP_HOST=0.0.0.0 \
    DEEPDEEP_PORT=5000 \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        "torch==2.14.0+cpu" \
    && python -m pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data/docs /root/.cache/huggingface

EXPOSE 5000

CMD ["python", "main.py", "--gui"]
