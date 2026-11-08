# Deploy the backend to GCP (free tier)

One e2-micro VM runs `api`, `outbox`, `agent-worker`, `memory-worker` and Caddy.
Postgres is on Neon. Redis is on Upstash.

## Stay at $0

- Region must be `us-central1`, `us-west1` or `us-east1`.
- Machine type must be `e2-micro`.
- Boot disk must be **Standard persistent disk**, 30 GB or less.
- Use the ephemeral external IP. Do not reserve a static IP.
- No snapshots, no second VM, no Cloud NAT, no load balancer.

## 1. Create the VM

1. Console → **Compute Engine → VM instances → Create instance**.
2. Name `ai-native-fpa`, region `us-west1` (Oregon, near Neon AWS us-west-2), zone `us-west1-b`.
3. Machine: **E2 → e2-micro**.
4. Boot disk → **Change** → Debian 12, **Standard persistent disk**, 30 GB.
5. Firewall: tick **Allow HTTP traffic** and **Allow HTTPS traffic**.
6. Click **Create**. Note the **External IP**, for example `34.123.45.67`.

## 2. Install Docker and swap

From your Mac:

```bash
gcloud compute scp backend/deploy/setup-vm.sh ai-native-fpa:~ --zone us-west1-b
gcloud compute ssh ai-native-fpa --zone us-west1-b
bash setup-vm.sh
exit
```

Log in again so the `docker` group applies.

## 3. Copy the code and the prod env

On the VM:

```bash
git clone https://github.com/<you>/ai-native-fpa.git
```

From your Mac:

```bash
gcloud compute scp backend/.env.prod ai-native-fpa:~/ai-native-fpa/backend/.env.prod --zone us-west1-b
```

`.env.prod` must have:

```
ENVIRONMENT=production
DATABASE_URL=<the Neon URL>
REDIS_URL=<the Upstash rediss:// URL>
COOKIE_SECURE=true
API_DOMAIN=34-123-45-67.sslip.io
REDIS_BLOCK_MS=60000
OUTBOX_IDLE_SLEEP_SECONDS=1800
RUN_SWEEP_INTERVAL_SECONDS=1800
```

`API_DOMAIN` is the external IP with dashes, plus `.sslip.io`. It needs no setup.

The last three slow the idle loops, so Neon can sleep and Upstash stays under its free limit.
Memories save up to 30 minutes late. Chat itself is not delayed.

## 4. Migrate and start

On the VM, in `~/ai-native-fpa/backend`:

```bash
docker compose --env-file .env.prod build
docker compose --env-file .env.prod run --rm api alembic upgrade head
docker compose --env-file .env.prod up -d
```

Check: `curl https://34-123-45-67.sslip.io/health`

## 5. Point the frontend at it

On the frontend host, set `BACKEND_ORIGIN=https://34-123-45-67.sslip.io` and redeploy.

## Update after a code change

```bash
cd ~/ai-native-fpa && git pull
cd backend
docker compose --env-file .env.prod up -d --build
```

Run `alembic upgrade head` again when a new migration is added.

## Debug

```bash
docker compose --env-file .env.prod ps
docker compose --env-file .env.prod logs -f --tail 100 agent-worker
free -h
```

## If the VM is stopped and started

The ephemeral IP can change. Update `API_DOMAIN` and `BACKEND_ORIGIN`, then `up -d` again.
