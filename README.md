# Docker template (Alpine base)

This repository contains a minimal Docker template using Alpine Linux as the base image.

Build the image:

```bash
docker build -t scan-splitter:latest .
```

Run with docker:

```bash
docker run --rm -it -v "$(pwd)":/app scan-splitter:latest
```

Run with docker-compose:

```bash
docker-compose up --build
```

Adjust the `Dockerfile` and `docker-compose.yml` to fit your project's runtime and entrypoint.
