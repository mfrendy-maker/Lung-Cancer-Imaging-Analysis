FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    LUNG_GUI_HOST=0.0.0.0 LUNG_GUI_DEMO=1 LUNG_GUI_TRUST_PROXY=1 LUNG_GUI_MAX_MB=10

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install .

RUN useradd --create-home appuser
USER appuser

# The platform provides PORT; LUNG_GUI_TOKEN must be set as a secret environment variable.
CMD ["python", "-m", "lung_imaging_analysis.lung_gui"]
