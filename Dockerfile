FROM python:3.11-slim

WORKDIR /app

# Build deps mínimos (numpy/scipy a veces los piden).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Torch CPU-only (~700MB) ANTES de transformers, así pip no baja la versión
# con CUDA por defecto (que pesa ~2GB). Transformers detecta el torch ya
# instalado y no lo reemplaza.
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# Resto de las deps.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelo de SpaCy en español (~560MB) — necesario para P2 (lematización).
RUN python -m spacy download es_core_news_lg

# Datos de NLTK necesarios para P3 (Snowball stemming):
#   - punkt / punkt_tab : tokenizadores
#   - stopwords         : lista de stopwords del español
RUN python -m nltk.downloader -d /usr/share/nltk_data \
        punkt punkt_tab stopwords
ENV NLTK_DATA=/usr/share/nltk_data

# Pre-descarga del modelo SPLADE (~270MB) para que la primera consulta no
# pague la latencia de descarga. Si se requiere cambiar el modelo, exporte
# SPLADE_MODEL como variable de entorno y reconstruya la imagen.
ARG SPLADE_MODEL=naver/splade-cocondenser-ensembledistil
ENV SPLADE_MODEL=${SPLADE_MODEL}
RUN python -c "import os; \
from transformers import AutoTokenizer, AutoModelForMaskedLM; \
m = os.environ['SPLADE_MODEL']; \
AutoTokenizer.from_pretrained(m); \
AutoModelForMaskedLM.from_pretrained(m); \
print('[splade] cached', m)"

# Path donde docker-compose monta Vectorizacion/sparse-benchmark/src
# (read-only). El adapter en src/preprocess_adapter.py lo agrega a sys.path.
ENV VECTORIZACION_PATH=/app/sparse_benchmark
ENV PYTHONUNBUFFERED=1

CMD ["bash"]
