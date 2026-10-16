FROM python:3.13-slim

WORKDIR /app

# CPU PyTorch needs OpenMP at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Embeddings run on CPU inside this container.
# The LLM is Ollama Cloud, so install the CPU PyTorch wheel first.
# The default PyPI torch wheel depends on NVIDIA CUDA libraries.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --upgrade-strategy only-if-needed -r requirements.txt \
    && python -c "import torch; assert torch.version.cuda is None, torch.__version__; print('torch', torch.__version__, 'cpu-only')"

COPY app ./app
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
