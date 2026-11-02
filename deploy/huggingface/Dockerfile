FROM python:3.12-slim

# Hugging Face Spaces runs containers as user 1000 and expects the app on port 7860.
RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    LUNG_GUI_HOST=0.0.0.0 GUI_PORT=7860 LUNG_GUI_DEMO=1 LUNG_GUI_TRUST_PROXY=1 LUNG_GUI_MAX_MB=10

WORKDIR /home/user/app
RUN python -m pip install --upgrade pip && \
    python -m pip install https://github.com/mfrendy-maker/Lung-Cancer-Imaging-Analysis/archive/refs/heads/main.zip

# LUNG_GUI_TOKEN must be added as a Space secret; the app refuses to start on 0.0.0.0 without it.
CMD ["python", "-m", "lung_imaging_analysis.lung_gui"]
