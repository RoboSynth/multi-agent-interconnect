FROM python:3.12-slim
WORKDIR /srv
COPY business/order_app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY business /srv/business
USER 65534:65534
CMD ["uvicorn", "business.order_app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
