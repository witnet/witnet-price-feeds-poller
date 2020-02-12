FROM python:3.8.0b1-alpine3.9

RUN ["apk", "add", "gcc", "musl-dev"]

# Copy context and cd into it
COPY / /
WORKDIR /

RUN ["pip", "install", "-r", "requirements.txt"]


ENTRYPOINT ["python", "price_feed_poller.py", "--config_file"]

CMD ["$1"]

