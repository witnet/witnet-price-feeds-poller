# Witnet Price Feeds Poller

## Basic setup

```console
virtualenv -p python3 .
source bin/activate
pip install -r requirements.txt
python price_feeds_poller.py
```

## Docker image building

### Automated builds

This repository automatically builds and publishes images on Docker Hub upon pushing a new git tag.

### Manual builds

Building the Docker image manually is also possible:

```console
docker build -t witnet/price-feeds-poller -f docker/Dockerfile .
```
