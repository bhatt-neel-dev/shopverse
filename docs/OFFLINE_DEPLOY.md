# Deploying to a host with no internet

The ShopVerse lab VM (**172.20.21.25**) sits behind egress filtering. This document records what
actually works there, because the normal `bootstrap.sh` path does not.

## What the VM can and cannot do

Measured on 2026-08-03:

| | Result |
|---|---|
| Outbound **HTTP** (:80) | works — `apt-get` is fine |
| Outbound **HTTPS** (:443) | **silently dropped.** TCP connects, then the TLS Client Hello gets no reply — SNI filtering. Blocked: docker.io, github.com, pypi.org, npmjs.org, google.com |
| Proxy | none configured |
| Appliance 172.16.14.71 (HTTPS) | **reachable** — only *external* HTTPS is filtered |
| Dev Mac (10.20.40.88) | reachable |

Two consequences:

1. **The VM cannot pull or build images.** Base images come from Docker Hub over HTTPS, and the
   builds themselves need Maven Central, npm, and PyPI — all HTTPS.
2. **Architecture differs.** The dev Mac is `arm64`; the VM is `amd64`. Images built on the Mac
   without `--platform linux/amd64` will not run.

## The approach that works: serve a registry from the dev machine

The VM can reach the Mac, and plain-HTTP registry traffic is not filtered.

### 1. Run a registry on the dev machine

```bash
docker run -d --name shopverse-registry -p 5005:5000 --restart unless-stopped registry:2
```

### 2. Build the app images for amd64

```bash
cd deploy
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build
```

### 3. Put base images into the registry

Copy them **registry-to-registry** rather than pulling locally first — on a multi-arch-capable
Docker Desktop the local tag resolves to the host's own architecture, so `docker tag` + `push`
ships arm64 even after an amd64 pull.

```bash
for i in mysql:8.4 postgres:16 mongo:7 redis:7-alpine rabbitmq:3.13-management-alpine; do
  docker buildx imagetools create --tag "localhost:5005/${i}" "mirror.gcr.io/library/${i}"
done
```

`mirror.gcr.io` is used instead of Docker Hub because anonymous Hub pulls hit `429 Too Many
Requests` quickly.

### 4. Push the app images

```bash
for i in catalog order cart search payment notify storefront gateway studio-api studio-ui locust seed; do
  docker tag "shopverse-${i}:latest" "localhost:5005/shopverse-${i}:latest"
  docker push "localhost:5005/shopverse-${i}:latest"
done
```

> Use `${i}` with braces. In zsh, `$i:latest` is parsed as the `:l` lowercase modifier and
> silently produces garbage tags like `shopverse-orderatest`.

### 5. Verify every image really is amd64

Do not trust `docker image inspect` on the dev machine — query the registry:

```bash
python3 forge/check_registry_arch.py            # prints OK/BAD per image
```

### 6. Trust the registry on the VM

```bash
printf '{ "insecure-registries": ["10.20.40.88:5005"] }\n' > /tmp/daemon.json
sudo cp /tmp/daemon.json /etc/docker/daemon.json
sudo systemctl restart docker
```

> Write the file first and `cp` it. `echo pw | sudo -S tee file <<EOF` fails, because the heredoc
> takes over stdin and the password never reaches sudo.

### 7. Deploy

```bash
cd ~/shopverse/deploy
printf 'REGISTRY=10.20.40.88:5005\nSTUDIO_API_PORT=9100\n' > .env
sudo docker compose -f docker-compose.yml -f docker-compose.registry.yml up -d
```

`docker-compose.registry.yml` swaps every `build:` for an `image:` reference, so nothing is
compiled on the VM.

## Docker on the VM

Installed from Ubuntu's own repos (HTTP), not `get.docker.com` (HTTPS):

```bash
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER     # re-login for this to take effect
```

Gives Docker 29.1.3 and Compose 2.40.3, both new enough.

## The better long-term fix

Ask the network team to allow HTTPS egress to `registry-1.docker.io`, `auth.docker.io`, and
`production.cloudflare.docker.com`, plus `github.com` if the VM should pull the repo directly.
Then `deploy/bootstrap.sh` works as written and the dev-machine registry is unnecessary.
