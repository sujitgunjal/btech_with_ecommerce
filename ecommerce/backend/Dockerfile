FROM python:3.13-slim

WORKDIR /srv

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/srv/backend
ENV SCENARIO_CATALOGUE_PATH=/srv/scenarios/catalogue.json

COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

COPY backend /srv/backend
COPY scenarios /srv/scenarios

WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "shop_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
