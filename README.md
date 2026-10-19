# Drop

A small FastAPI server for a lab that accepts file uploads over HTTP and stores
them in a local directory. Works from a browser, `curl`, and PowerShell.

> Use only against machines and networks you own or are explicitly authorized to test.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python3 ./main.py
```

Then open <http://localhost:8000/> for the upload page.

### Options (environment variables)

| Variable     | Default   | Meaning                                              |
|--------------|-----------|------------------------------------------------------|
| `HOST`       | `0.0.0.0` | Interface to bind.                                   |
| `PORT`       | `8000`    | Port to listen on.                                   |
| `UPLOAD_DIR` | `uploads` | Directory where received files are written.          |
| `AUTH_TOKEN` | *(unset)* | If set, every upload must present this token.        |
| `TRUST_PROXY`| *(unset)* | `1` to trust `X-Forwarded-For` (behind a proxy only). |

```bash
PORT=9001 UPLOAD_DIR=/data/incoming AUTH_TOKEN=s3cret python3 ./main.py
```

Pass `-t` with no value to generate a random token; it is printed in the
startup banner so you can copy it:

```bash
python3 ./main.py -t          # -> [*] token : 3q9V...
python3 ./main.py -t s3cret   # or choose your own
```

> Prefer `uvicorn dropzone.server:app --host 0.0.0.0 --port 8000` if you want auto-reload
> during development (`--reload`).

## Uploading

### Browser

Open `/`, drag files in (or click **browse**), optionally enter the token, hit **Upload**.

### curl — multipart form

```bash
curl -F "file=@report.pdf" http://HOST:8000/upload
# with a token:
curl -H "Authorization: Bearer s3cret" -F "file=@report.pdf" http://HOST:8000/upload
```

### curl — raw body

```bash
curl --data-binary @report.pdf http://HOST:8000/upload/report.pdf
```

### PowerShell

```powershell
# multipart form (PowerShell 6+)
Invoke-WebRequest -Uri "http://HOST:8000/upload" -Method Post -Form @{ file = Get-Item .\report.pdf }

# raw body (any version)
Invoke-WebRequest -Uri "http://HOST:8000/upload/report.pdf" -Method Put -InFile .\report.pdf

# with a token
Invoke-WebRequest -Uri "http://HOST:8000/upload/report.pdf" -Method Put -InFile .\report.pdf `
  -Headers @{ Authorization = "Bearer s3cret" }
```

### wget

```bash
wget --post-file=report.pdf --header="Content-Type: application/octet-stream" \
  http://HOST:8000/upload/report.pdf
```

## Endpoints

| Method | Path                 | Body              | Purpose                        |
|--------|----------------------|-------------------|--------------------------------|
| GET    | `/`                  | –                 | Browser upload page.           |
| POST   | `/upload`            | multipart form    | Upload with field name `file`. |
| PUT/POST | `/upload/{filename}` | raw bytes       | Upload a raw body.             |
| GET    | `/health`            | –                 | Status / configured dir.       |

## Storage layout

Uploads are grouped by the client's IP address:

```
uploads/
├── 10.10.14.7/
│   ├── report.pdf
│   └── creds.txt
└── 192.168.1.50/
    └── archive.zip
```

By default the direct socket address is used. When running behind a reverse
proxy, start with `--trust-proxy` (or `TRUST_PROXY=1`) to use the first entry of
`X-Forwarded-For` instead — never enable it when clients connect directly, since
the header is client-controlled.

## Notes

- Filenames are sanitized (`basename` + allow-list) to prevent path traversal,
  and existing files are not overwritten (a short suffix is added).
- There is no TLS here; put it behind a reverse proxy (or use an SSH tunnel) if
  you need the transfer encrypted.
```
