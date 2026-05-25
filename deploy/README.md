# Deploy InsightAI with systemd

Project path: **`/opt/InsightAI`**

## 1. Install on the server

```bash
sudo mkdir -p /opt/InsightAI
sudo chown "$USER:$USER" /opt/InsightAI   # or clone as root then chown insightai

cd /opt/InsightAI
git clone https://github.com/mrhib/InsightAI.git .   # or copy your tree

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-mssql.txt
pip install -r requirements-rag.txt
pip install -e .

cp .env.example .env
# Edit .env — production example:
#   INSIGHTAI_ENV=production
#   INSIGHTAI_API_RELOAD=false
#   INSIGHTAI_API_HOST=127.0.0.1
#   INSIGHTAI_API_PORT=8000
#   INSIGHTAI_CORS_ALLOW_ORIGINS=https://your-frontend.example.com
#   DB_HOST=127.0.0.1
#   DB_PORT=1434
```

## 2. Service user (recommended)

```bash
sudo useradd --system --home /opt/InsightAI --shell /usr/sbin/nologin insightai
sudo chown -R insightai:insightai /opt/InsightAI
sudo chmod 600 /opt/InsightAI/.env
```

## 3. Install units

```bash
sudo cp /opt/InsightAI/deploy/insightai.service /etc/systemd/system/
# Optional — remote MSSQL via SSH:
# Edit deploy/insightai-mssql-tunnel.service (user@host), then:
# sudo cp /opt/InsightAI/deploy/insightai-mssql-tunnel.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable insightai-mssql-tunnel.service   # if used
sudo systemctl enable insightai.service
sudo systemctl start insightai-mssql-tunnel.service    # if used
sudo systemctl start insightai.service
```

## 4. Verify

```bash
sudo systemctl status insightai.service
curl -s http://127.0.0.1:8000/api/v1/health
curl -s http://127.0.0.1:8000/health/ready | jq
sudo journalctl -u insightai.service -f
```

## 5. Reload after deploy

```bash
cd /opt/InsightAI
git pull
source .venv/bin/activate
pip install -r requirements-mssql.txt -r requirements-rag.txt
pip install -e .
sudo systemctl restart insightai.service
```

Put nginx or another reverse proxy in front if exposing the API outside localhost.
