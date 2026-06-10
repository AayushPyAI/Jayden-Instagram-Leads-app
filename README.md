# Instagram Leads — User & Operations Guide

Web application that turns Instagram profile screenshots into structured call-list data. Google Gemini reads each image and extracts business name, phone, email, and Instagram handle. The app then checks your existing Excel workbooks for duplicates and saves results to cloud storage.

This document is written for day-to-day users and for the team managing hosting and credentials.

---

## Quick start (end users)

1. Open the app in your browser (your team admin will provide the URL).
2. Go to **Folders** and confirm your reference workbooks are in **MASTER** (see [Workbook folders](#workbook-folders)).
3. Return to **AI Processing**.
4. Upload screenshots (drag and drop, choose files, or choose a folder).
5. Click **Process** and wait for extraction to finish.
6. Review the results table — edit any cell directly if the AI missed or misread something.
7. Choose how to save (new workbook or append to an existing MASTER file), then confirm.

Supported screenshot formats: PNG, JPG, JPEG, WebP.

---

## AI Processing — step by step

### 1. Duplicate check workbooks

Before processing, choose which MASTER workbooks to compare against:

- **All workbooks (default)** — every `.xlsx` file in MASTER is used.
- **Specific files** — open the dropdown and tick only the workbooks you want.

Duplicate detection reads the **first sheet** of each workbook.

### 2. Upload screenshots

- Drag files or an entire folder onto the drop zone, or click to browse.
- A preview row shows thumbnails; click a thumbnail to view full size.
- You can add more files in multiple steps before processing.

### 3. Process

Click **Process**. A progress modal shows how many screenshots have been handled. Large batches are sent in smaller chunks automatically.

When finished you will see:

- **New** — leads not found in your MASTER lists.
- **Duplicates** — leads that match an existing row (or another screenshot in the same batch).

### 4. Review and edit

The **Extracted Data** table shows one row per screenshot. Columns typically include:

| Column | Description |
|--------|-------------|
| Business Name | Name shown on the profile |
| Mobile | Phone number |
| Email | Email address if visible |
| Instagram | Handle or profile URL |
| Date & Time | When the row was processed |
| Duplicate Source File / Row | Where a duplicate was found (if applicable) |
| Image Name | Original screenshot filename |

Use the pagination controls for large result sets. Status badges mark each row as **New** or **Duplicate**.

**Copy buttons** — quickly copy Instagram handles and phone numbers to your clipboard:

- Copy New Leads
- Copy Duplicate Leads
- Copy All

### 5. Save results

| Save mode | What it does |
|-----------|----------------|
| **Save as New** | Creates new `.xlsx` file(s) in cloud storage. New leads go to **NEW/**; duplicates go to **DUPLICATE/**. You will be asked to name the export. |
| **Save to Existing** | Appends selected rows into a workbook already in **MASTER/**. Pick the target sheet from the dropdown. |

**Rows to save** — choose New leads only, Duplicates only, or All rows.

Click **Confirm** to write to storage, or **Cancel** to discard the session and start over.

---

## Folders page

Use **Folders** in the sidebar to manage workbooks in cloud storage (S3 in production).

| Folder | Purpose |
|--------|---------|
| **MASTER** | Your reference call lists. Upload existing `.xlsx` files here for duplicate checking. You can also append processed leads back into a MASTER workbook. |
| **NEW** | Exports of non-duplicate leads (created when you use Save as New). |
| **DUPLICATE** | Exports of duplicate leads (created when you use Save as New). |

From this page you can upload `.xlsx` files to MASTER, download files, rename them, and delete them. Click **Refresh** to reload the file list.

---

## Workbook format requirements

MASTER workbooks must be standard Excel `.xlsx` files. The app maps columns on the **first sheet** to these fields (header names are matched flexibly):

- **Business Name**
- **Mobile** (phone)
- **Email**
- **Instagram** (handle or URL)

If a column cannot be mapped, duplicate checking for that field may be incomplete. Keep column headers clear and consistent across files.

---

## Troubleshooting (users)

| Problem | What to try |
|---------|-------------|
| No duplicates detected but you expect some | Confirm `.xlsx` files are in **MASTER** on the Folders page. Check that column headers match the expected names. |
| Wrong or missing fields after processing | Edit cells in the results table before saving. Ensure screenshots clearly show the profile info. |
| Upload rejected | Only PNG/JPG/JPEG/WebP images are accepted. Very large batches may be limited — process in smaller groups. |
| Processing is slow | Normal for many screenshots; each image is sent to the AI separately. Wait for the progress modal to finish. |
| Cannot see saved files | Open **Folders**, select the correct folder (NEW or DUPLICATE), and click **Refresh**. |
| Server busy message | The app retries automatically. If it persists, wait a minute and try again with fewer screenshots. |

---

## Production environment

The live app runs on AWS. Your administrator manages access.

| Item | Value |
|------|-------|
| Region | `us-east-1` |
| Port | `8501` |
| Workbook storage | Amazon S3 |
| S3 bucket | `YOUR_S3_BUCKET` |
| S3 prefix | `prod/` |
| Logs | CloudWatch `/ecs/instagram-leads-prod` |

Workbooks are stored under `s3://YOUR_S3_BUCKET/prod/` in the MASTER, NEW, and DUPLICATE subfolders.

---

## Local development (technical team)

For running the app on a developer machine.

### Requirements

- Python 3.12+
- Google Gemini API key
- AWS credentials with access to the S3 bucket

### Setup

```bash
cd Jayden
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your credentials (see `.env.example` for all options). **Never commit `.env`.**

### Run

```bash
source .venv/bin/activate
uvicorn app:app --reload --host 0.0.0.0 --port 8501
```

Open http://localhost:8501 — health check: `GET /health` returns `{"status":"ok"}`.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `S3_BUCKET` | Yes | S3 bucket for workbooks |
| `S3_PREFIX` | Yes | Prefix under bucket (e.g. `prod`) |
| `AWS_DEFAULT_REGION` | Yes | AWS region (e.g. `us-east-1`) |
| `AWS_ACCESS_KEY_ID` | Local dev | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Local dev | AWS secret key |
| `PORT` | No | Default `8501` |
| `LOG_LEVEL` | No | Default `INFO` |
| `GEMINI_MODEL` | No | Default `models/gemini-2.5-flash` |
| `PROCESS_CHUNK_SIZE` | No | Screenshots per API request |
| `MAX_SCREENSHOTS_PER_REQUEST` | No | Hard cap per upload |

Optional export and column tuning is configured in `config.py` or via environment variables documented in `.env.example`.

### Batch CSV export (CLI)

Extract a folder of screenshots to CSV without the web UI:

```bash
source .venv/bin/activate
python scripts/export_folder_leads_csv.py /path/to/screenshots -o leads.csv
```

---

## Deployment (technical team)

Production runs on **AWS ECS Fargate**. Prerequisites: Docker, AWS CLI authenticated to the deployment account.

```bash
./deploy/ecs-prod-rollout.sh
```

This builds a `linux/amd64` image, pushes to ECR (`instagram-leads-api`), registers the ECS task definition, and forces a new deployment on service `YOUR_ECS_SERVICE` in cluster `production`.

Override defaults if needed:

```bash
ECS_CLUSTER=production \
ECS_SERVICE=YOUR_ECS_SERVICE \
IMAGE_TAG=latest \
./deploy/ecs-prod-rollout.sh
```

The Gemini API key in production is stored in AWS Secrets Manager (`YOUR_GEMINI_SECRET_NAME`), not in the Docker image.

---

## Project structure

```
Jayden/
├── app.py                 # Web API and routes
├── config.py              # Settings and extraction prompts
├── processor.py           # Gemini extraction, dedup, Excel logic
├── workbook_storage.py    # S3 workbook storage
├── logging_config.py      # Structured logging
├── static/                # Frontend CSS and JavaScript
├── templates/             # HTML UI
├── deploy/                # ECS production rollout scripts
├── scripts/               # CLI utilities
├── Dockerfile
├── requirements.txt
└── .env.example           # Environment template (copy to .env)
```

---

## Security

- Do not share API keys, AWS credentials, or `.env` files.
- Rotate credentials immediately if they are ever exposed.
- Production secrets live in AWS Secrets Manager, not in source code.

---

## Tech stack

- **Backend:** FastAPI, Uvicorn, boto3, pandas, openpyxl
- **AI:** Google Gemini
- **Frontend:** HTML, CSS, JavaScript (Jinja2 templates)
- **Hosting:** AWS ECS Fargate, ECR, S3, Application Load Balancer, CloudWatch
