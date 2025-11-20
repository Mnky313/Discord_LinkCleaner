FROM python
COPY ./LinkCleaner/ /app
WORKDIR /app
RUN apt-get update -qq && apt-get install ffmpeg -y
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
CMD ["python", "./main.py"]

