# Deploying MediNexus AI to Azure

MediNexus runs on **one Linux virtual machine**: nginx serves the React app and forwards `/api` to
the FastAPI service on the same machine. One machine is a requirement, not a shortcut: the database
is a single DuckDB file that allows one writing process, and the morning sweep (and the optional
nightly data feed) run inside the API. Do not put it behind a scale-out service (App Service with several
instances, Container Apps replicas) or on network file storage (Azure Files).

```
browser ──HTTPS──> nginx (port 443) ──> /            React build (frontend/dist)
                                    └──> /api/*      uvicorn, 127.0.0.1:8000, one process
                                                      └── database/healthcare.duckdb (VM disk)
```

Time: about 45 minutes the first time. Files used: `deploy/pack_data.py`, `deploy/setup_server.sh`,
`deploy/update.sh`, `deploy/nginx.conf`, `deploy/medinexus-api.service`.

## 1. Create the virtual machine (Azure portal, ~10 min)

Sign in at https://portal.azure.com → **Create a resource** → **Virtual machine**.

| Setting | Value |
|---|---|
| Resource group | Create new: `medinexus-rg` |
| Virtual machine name | `medinexus-vm` |
| Region | The one closest to your users (e.g. Central India) |
| Availability options | No infrastructure redundancy required |
| Image | **Ubuntu Server 24.04 LTS – x64 Gen2** |
| Size | **Standard_B2ms** (2 vCPU, 8 GB RAM). B2s (4 GB) is cheaper but tight for the nightly rebuild |
| Authentication type | SSH public key |
| Username | `azureuser` |
| SSH public key source | Generate new key pair (you download a `.pem` file at the end) |
| Public inbound ports | Allow selected ports: **SSH (22), HTTP (80), HTTPS (443)** |
| Disks → OS disk size | 64 GiB, Standard SSD |

Leave the other tabs at their defaults → **Review + create** → **Create** → **Download private key
and create resource**. Save the key as `C:\Users\<you>\.ssh\medinexus-vm.pem`.

When it is ready, open the VM in the portal:

1. **Give it a name.** Overview → *DNS name* → **Not configured** → set *DNS name label* to
   something unique, e.g. `medinexus-demo` → Save. Your address becomes
   `medinexus-demo.<region>.cloudapp.azure.com` (shown on the Overview page). The HTTPS certificate
   is issued for this name.
2. **Lock down SSH.** Networking → Network settings → the inbound rule for port 22 → *Source*:
   **My IP address** → Save. Ports 80 and 443 stay open to everyone.

Cost: B2ms is roughly USD 60–70 a month if it runs all the time (check the Azure pricing calculator for
your region). **Stop** the VM in the portal when you are not using it to stop paying for compute; the
disk and the DNS name are kept. The dataset is fixed, so nothing needs to catch up after a restart.

## 2. Package the data (your laptop, ~3 min)

The database, models and data files are not in git. Stop the app (close `npm run dev`), then in the
project folder:

```bash
python deploy/pack_data.py
```

This writes `medinexus_data.tar.gz` (about 280 MB): the database with all accounts, trained models,
the Synthea download and the re-dated data. It skips your upload sandboxes and backups.

Windows only, once: SSH refuses a key file other users can read. In PowerShell:

```powershell
icacls $env:USERPROFILE\.ssh\medinexus-vm.pem /inheritance:r /grant:r "$($env:USERNAME):R"
```

Copy the package to the VM (replace the address with yours):

```bash
scp -i ~/.ssh/medinexus-vm.pem medinexus_data.tar.gz azureuser@medinexus-demo.centralindia.cloudapp.azure.com:~/
```

## 3. Install on the VM (~15 min)

Connect:

```bash
ssh -i ~/.ssh/medinexus-vm.pem azureuser@medinexus-demo.centralindia.cloudapp.azure.com
```

On the VM, get the code and run the setup script with your address, an email for certificate
notices, the package and your time zone (the 07:00 morning sweep uses it):

```bash
git clone https://github.com/tejaswinimallick21-lang/MediNexus-AI.git medinexus
cd medinexus
bash deploy/setup_server.sh --domain medinexus-demo.centralindia.cloudapp.azure.com --email you@example.com --data ~/medinexus_data.tar.gz --timezone Asia/Kolkata
```

If the repository is private, git asks for a username and password: use your GitHub username and
a personal access token with read-only access to this repository.

The script installs Python, Node and nginx, adds a swap file, unpacks the data, builds the web app,
creates `.env` with a new session key (`MEDINEXUS_ENV=production`, secure cookies), starts the API
as a service, configures nginx and gets a free Let's Encrypt certificate (by running it you accept
Let's Encrypt's terms). It ends with `API is up. Open https://...`.

**AI answers (optional).** Without a key, Nexa uses the free rules engine. To use OpenAI:

```bash
nano .env          # set OPENAI_API_KEY=..., save with Ctrl+O, exit with Ctrl+X
sudo systemctl restart medinexus-api
```

Anyone who can sign in then spends your credit (the per-question caps still apply), so keep the
number of accounts small.

## 4. First sign-in and hardening (~5 min)

1. Open `https://<your address>` and sign in with your admin account (the same accounts as on your
   laptop, because the database was copied).
2. **Change the demo passwords.** Security → People: reset the starter accounts, or disable them
   and add a personal account for each person who needs access. Until then the Security page
   shows *Default passwords: fail* (production mode is strict), and anyone who has read the
   README can sign in.
3. Security → Overview should show the session key and secure cookies as passed.
4. Data Engineering → Dataset shows the same "data through" date as on your laptop.

## Running it

| Task | Command (on the VM, in `~/medinexus`) |
|---|---|
| Live API log | `sudo journalctl -u medinexus-api -f` |
| Restart the API | `sudo systemctl restart medinexus-api` |
| Deploy new code from GitHub | `bash deploy/update.sh` |
| Back up the database | `sudo systemctl stop medinexus-api && cp database/healthcare.duckdb ~/healthcare-$(date +%F).duckdb && sudo systemctl start medinexus-api` |
| Disk space | `df -h /` |

For automatic backups, turn on **Backup** for the VM in the portal (daily snapshot of the whole disk).

The HTTPS certificate renews itself (certbot's timer). Push code to GitHub as usual, then run
`deploy/update.sh` on the VM; data, accounts and `.env` are not touched.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `502 Bad Gateway` | The API is not running: `sudo journalctl -u medinexus-api -n 100`, fix, then restart it |
| Certificate step fails | The DNS name label is not set, or port 80 is closed in the VM's network rules |
| Sign-in works, then you are signed out at once | Opened over `http://` while secure cookies are on: use `https://` |
| `Permission denied (publickey)` | Wrong key or user: `ssh -i <the .pem> azureuser@...` |
| `UNPROTECTED PRIVATE KEY FILE` on Windows | Run the `icacls` command in step 2 |
| Pages slow or the API restarts | Out of memory: resize the VM to B4ms (portal → Size) |

## What this setup is not

It is a single-server deployment for a demo or a pilot on synthetic data. Real patient data would
need, at least, Azure's HIPAA/BAA terms, private networking (no public IP, access through a VPN or
Azure Bastion), disk encryption with your own keys, single sign-on, central log monitoring and a
tested backup and restore. Plan those before any real data reaches the server.
