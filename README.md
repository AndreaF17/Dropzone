# DropZone

A small FastAPI server for a lab that accepts file uploads over HTTP and stores
them in a local directory. Works from a browser, `curl`, and PowerShell.

> Use only against machines and networks you own or are explicitly authorized to test.

## Install

Requires Python 3.10+. Installing puts a `dz` command on your `PATH`.

### pipx (recommended)

[pipx](https://pipx.pypa.io/) installs the tool into its own isolated
environment:

```bash
pipx install git+https://github.com/AndreaF17/dropzone.git
# or, from a local checkout:
pipx install .
```

Upgrade with `pipx upgrade dropzone`, remove with `pipx uninstall dropzone`.

### pip

Inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install git+https://github.com/AndreaF17/dropzone.git
# or, from a local checkout:
pip install .
```

### From source (no install)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 ./main.py                # same options as dz
```

## Run

```bash
dz                               # or: python -m dropzone / python3 ./main.py
```

Then open <http://localhost:8000/> for the upload page.

### Command-line options

| Flag                  | Default    | Meaning                                                        |
|-----------------------|------------|----------------------------------------------------------------|
| `-H, --host HOST`     | `0.0.0.0`  | Interface to bind.                                             |
| `-p, --port PORT`     | `8000`     | Port to listen on.                                             |
| `-d, --dir DIR`       | `uploads`  | Directory where received files are written.                    |
| `-t, --token [TOKEN]` | *(none)*   | Require a bearer token; with no value one is generated.        |
| `--trust-proxy`       | off        | Use `X-Forwarded-For` for the client IP (behind a proxy only). |
| `-v, --verbose`       | off        | Also show uvicorn startup and per-request access logs.         |
| `--no-color`          | off        | Disable colored output (also `NO_COLOR=1`).                    |
| `--reload`            | off        | Auto-reload on code changes (development).                     |
| `-V, --version`       |            | Print the version and exit.                                    |

By default the console only shows received files, rejected uploads (missing
or wrong token) and errors.

### Environment variables

Each flag's default can also be set from the environment:

| Variable     | Default   | Meaning                                              |
|--------------|-----------|------------------------------------------------------|
| `HOST`       | `0.0.0.0` | Interface to bind.                                   |
| `PORT`       | `8000`    | Port to listen on.                                   |
| `UPLOAD_DIR` | `uploads` | Directory where received files are written.          |
| `AUTH_TOKEN` | *(unset)* | If set, every upload must present this token.        |
| `TRUST_PROXY`| *(unset)* | `1` to trust `X-Forwarded-For` (behind a proxy only). |

```bash
PORT=9001 UPLOAD_DIR=/data/incoming AUTH_TOKEN=s3cret dz
```

Pass `-t` with no value to generate a random token; it is printed in the
startup banner so you can copy it:

```bash
dz -t          # -> [*] token : 3q9V...
dz -t s3cret   # or choose your own
```

> During development, `dz --reload` restarts the server on code changes
> (or run `uvicorn dropzone.server:app --reload` directly).

## Usage

```text
usage: dz [-h] [-H HOST] [-p PORT] [-d DIR] [-t [TOKEN]] [--trust-proxy]
          [--reload] [--no-color] [-v] [-V]
```

Run `dz --help` for the full option list (see the table above).

### Common setups

```bash
dz                                   # open server on 0.0.0.0:8000, files in ./uploads
dz -t                                # require a generated token (shown in the banner)
dz -t s3cret -p 9001                 # your own token, custom port
dz -H 127.0.0.1 -d ~/loot            # bind to localhost only, custom upload dir
dz -t --trust-proxy                  # behind a reverse proxy (nginx, caddy, ...)
dz -v                                # full uvicorn startup + access logs
```

### Example session

Start the server with a generated token:

```console
$ dz -t
  ...
  [*] listening : http://0.0.0.0:8000
  [*] storing   : /home/me/uploads/<client-ip>/
  [*] auth      : bearer token required
  [*] token     : uOdyF12TkI75iNaJGQjwYIfB
  [*] received files are logged below; Ctrl-C to stop
```

From the other machine, send a file with that token:

```bash
curl -H "Authorization: Bearer uOdyF12TkI75iNaJGQjwYIfB" -F "file=@report.pdf" http://10.10.14.2:8000/upload
# -> {"saved":"report.pdf","dir":"10.10.14.7","bytes":48213}
```

The server console shows what arrived (and any rejected attempts):

```text
14:43:04 WARN  dropzone: deny 10.10.14.7      missing token
14:43:09 INFO  dropzone: recv 10.10.14.7      report.pdf      48213 bytes -> /home/me/uploads/10.10.14.7/report.pdf
```

Stop with `Ctrl-C`; files stay in `uploads/<client-ip>/`.

## Uploading

### Browser

Open `/`, drag files in (or click **browse**), optionally enter the token, hit **SEND**.

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
