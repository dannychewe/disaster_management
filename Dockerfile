FROM python:3.11

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y \
  binutils libproj-dev gdal-bin libgdal-dev && \
  rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN pip install --no-cache-dir \
    pandas \
    scikit-learn \
    xgboost \
    prophet \
    statsmodels \
    joblib

COPY . .

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
