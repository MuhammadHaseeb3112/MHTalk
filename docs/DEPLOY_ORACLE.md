# Deploying MHTalk on Oracle Cloud (Always Free), step by step

At the end of this guide MHTalk runs on your own Linux server at
`https://<yourname>.duckdns.org`, with HTTPS, voice/video calls (TURN relay),
push notifications and automatic restarts. It costs nothing, as long as you stay
inside the Always Free limits.

What you will use (all free):

| Piece | Service |
|---|---|
| Server | Oracle Cloud Always Free, Ampere A1 VM (2 OCPU, 12 GB RAM, Ubuntu 24.04 Arm) |
| Domain | DuckDNS sub-domain (`yourname.duckdns.org`) |
| HTTPS | Caddy (inside the stack), automatic Let's Encrypt certificate |
| Code | GitHub repository |

> **Limits to respect.** The Always Free Ampere A1 allowance is **2 OCPU and 12 GB
> memory in total** (it was 4/24 before mid-2026). Never create A1 machines that
> add up to more than that. If you do, Oracle disables *all* A1 machines when the
> trial ends.

---

## Step 0. Put the code on GitHub

The server downloads the code from GitHub.

1. Install **GitHub Desktop** (https://desktop.github.com) and sign in.
2. *File → Add local repository →* `D:\Projects\Django\MHTalk`.
3. Check the list of changed files. **`.env`, `*.sqlite3`, `sqlite_backup.json`
   and `media/` must NOT appear** (they are git-ignored). If one does, stop and fix
   `.gitignore` first.
4. Write a summary such as "Production-ready MHTalk", then click **Commit**, then **Push origin**.

## Step 1. Create the Oracle Cloud account

1. Go to https://www.oracle.com/cloud/free/ and click **Start for free**.
2. **Home region:** pick one close to your users that has Arm capacity, for example
   *UAE East (Dubai)* or *India West (Mumbai)*. **It can never be changed later.**
3. Verify your phone number and add a card. Oracle uses the card to verify you
   and says it does not charge it for Always Free resources. Oracle places a
   small temporary hold (about $1) that the bank releases in a few days.
4. Wait for the "account is ready" email (it can take from minutes to a few hours).

## Step 2. Create the server (VM)

1. Console → ☰ → **Compute → Instances → Create instance**.
2. **Name:** `mhtalk`.
3. **Image:** *Change image →* **Canonical Ubuntu 24.04** (the *aarch64* build is chosen automatically for Arm).
4. **Shape:** *Change shape → Ampere →* **VM.Standard.A1.Flex**, **2 OCPU, 12 GB** memory.
5. **Networking:** keep "Create new virtual cloud network" and **Assign a public IPv4 address = Yes**.
6. **SSH keys:** *Generate a key pair for me →* **Save private key**. Keep the
   `.key` file safe; it is the only way into the server.
7. **Boot volume:** the default 50 GB is fine (Always Free includes 200 GB in total).
8. Click **Create**. If you see *"Out of capacity"*, try a different
   Availability Domain or try again later. Capacity frees up during the day.
9. When the state is **Running**, copy the **Public IP address**.

## Step 3. Open the firewall (two places)

**A. Oracle network (security list).** Instance page → *Primary VNIC → Subnet →
Security → Default Security List → Add Ingress Rules*. Use source `0.0.0.0/0` for each rule:

| Protocol | Destination port | Why |
|---|---|---|
| TCP | 80 | HTTP (certificate check + redirect) |
| TCP | 443 | HTTPS / WebSockets |
| UDP | 443 | HTTP/3 |
| TCP + UDP | 3478 | TURN (calls) |
| UDP | 49160-49200 | TURN relay ports |

**B. Ubuntu firewall.** Run these on the server (Step 5 shows how to connect):

```bash
sudo iptables -I INPUT 6 -p tcp -m multiport --dports 80,443,3478 -j ACCEPT
sudo iptables -I INPUT 6 -p udp -m multiport --dports 443,3478 -j ACCEPT
sudo iptables -I INPUT 6 -p udp --dport 49160:49200 -j ACCEPT
sudo netfilter-persistent save
```

## Step 4. Free domain (DuckDNS)

1. Go to https://www.duckdns.org and sign in (with Google or GitHub).
2. Add a sub-domain, e.g. `mhtalk`. In **current ip**, paste the server's public IP and click **update ip**.
3. Your address is now `mhtalk.duckdns.org`.

## Step 5. Connect to the server

Windows Terminal / PowerShell, in the folder that holds the key:

```powershell
ssh -i .\ssh-key-mhtalk.key ubuntu@<PUBLIC_IP>
```

(If Windows complains about key permissions: right-click the key → Properties →
Security → Advanced → disable inheritance → leave only your user.)

## Step 6. Install Docker and get the code

```bash
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker
git clone https://github.com/<github-user>/<repository>.git mhtalk
cd mhtalk
```

## Step 7. Production settings

```bash
cp deploy/env.prod.example .env.prod
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # use for SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # use for POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # use for TURN_SECRET
nano .env.prod
```

Fill in your domain everywhere (`DOMAIN`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
`CORS_ALLOWED_ORIGINS`, `TURN_URLS`) and the generated secrets. Optional:
`MHTALK_AI_API_KEY` (free Gemini key) and the push-notification keys
(Step 8). Save with **Ctrl+O**, **Enter**, **Ctrl+X**.

## Step 8. Start everything

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile turn up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod ps          # all "running"/"healthy"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py createsuperuser
```

Push notifications (optional): generate keys once, put them in `.env.prod`,
then run the `up -d` command again:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py generate_vapid_keys
```

The first build takes a few minutes. Open `https://mhtalk.duckdns.org`
and the padlock should appear. Admin: `/admin/`, API docs: `/api/docs/`.

## Step 9. Check it works

- `https://<domain>/api/health/` returns `{"status": "ok", ...}`.
- Register two accounts (phone + laptop) and send messages, photos and voice notes.
- Make a voice call with one phone on **mobile data** (not Wi-Fi). This proves TURN works.
- On the phone: browser menu → **Add to Home screen / Install app**.

## Day-2 operations

| Task | Command (inside `~/mhtalk`) |
|---|---|
| Update to the latest code | `bash deploy/deploy.sh` (build, restart, health check, automatic rollback) |
| Logs | `docker compose -f docker-compose.prod.yml logs -f web` |
| Restart | `docker compose -f docker-compose.prod.yml --env-file .env.prod restart web` |
| Database backup | `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U mhtalk mhtalk > ~/backup-$(date +%F).sql` |

### Nightly backups

`deploy/backup.sh` writes a compressed database dump to `~/backups` (kept 14
days). Run it every night at 03:00: `mkdir -p ~/backups`, then `crontab -e` and add

```cron
0 3 * * * cd ~/mhtalk && bash deploy/backup.sh >> ~/backups/backup.log 2>&1
```

**Copy backups off the server.** A backup on the same machine is lost with the
machine. Oracle's Always Free tier includes 20 GB of Object Storage, which is
separate from the VM:

1. Console → ☰ → **Storage → Buckets → Create bucket**, name `mhtalk-backups`
   (Standard tier, private).
2. Console → your profile (top right) → **My profile → Customer secret keys →
   Generate secret key**. Copy the secret (shown once) and the access key.
3. Note your **namespace** (Console → ☰ → Governance → Tenancy details →
   *Object storage namespace*).
4. On the server:

```bash
sudo apt -y install rclone
rclone config create oci s3 provider=Other \
  access_key_id=<access key> secret_access_key=<secret> \
  endpoint=https://<namespace>.compat.objectstorage.me-dubai-1.oraclecloud.com \
  region=me-dubai-1 force_path_style=true no_check_bucket=true
```

5. In `.env.prod` set `BACKUP_REMOTE=oci:mhtalk-backups`, then test with
   `bash deploy/backup.sh` and `rclone ls oci:mhtalk-backups`.

Restore: see the comment at the top of `deploy/backup.sh`.


### Monitoring and keeping it free

**Uptime monitoring (free):** add `https://<domain>/api/health/` to
https://uptimerobot.com to get an email if the site goes down.

**Idle reclaim:** Oracle may reclaim Always Free machines that stay almost idle
for a long time. Real usage plus the health checks keep it active. Sign in to the
console at least once a month too.

**Keep it at $0:** never click *Upgrade* (to *Pay As You Go*). Without the
upgrade, Oracle can't bill you: when the 30-day trial ends, only Always Free
resources keep running. Create only the one A1 VM described here (2 OCPU, 12 GB,
default boot volume) and add a $1 budget alert (☰ → Billing & Cost Management →
Budgets) so you get an email if anything ever costs money.

**DuckDNS IP:** Oracle keeps the same public IP while the VM exists, so this is
a one-time setting. If you ever recreate the VM, update the IP on duckdns.org.

## Automatic deploys (CD)

After this, every push to `main` deploys itself: GitHub Actions runs the tests
(CI), then SSHes into the server and runs `deploy/deploy.sh`, which builds,
restarts, waits for the health check and **rolls back to the previous version
on its own** if the new one isn't healthy. Workflow: `.github/workflows/deploy.yml`.

1. In the GitHub repository: **Settings → Secrets and variables → Actions**.
2. **Secrets** tab → *New repository secret*, three times:
   - `DEPLOY_HOST`: the server's public IP
   - `DEPLOY_USER`: `ubuntu`
   - `DEPLOY_SSH_KEY`: the whole content of the private `.key` file from Step 2
3. **Variables** tab → *New repository variable*, twice:
   - `DEPLOY_ENABLED`: `true`
   - `DEPLOY_URL`: `https://<your domain>`
4. Test it: **Actions → Deploy → Run workflow**. The log ends with
   "Healthy. Deployed …".

Until `DEPLOY_ENABLED` is `true` the Deploy workflow is skipped, so pushing
before the server exists is safe.
