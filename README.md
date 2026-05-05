# Cluster Browser

Desktop SFTP file browser for lab users, built with Python, Paramiko, and PySide6.

The app connects to a remote SSH/SFTP server, limits browsing to the logged-in user's home directory under `/data/home/<username>`, and provides a desktop UI for navigating folders, previewing supported files, downloading files locally, and opening files with the system default application.

## What It Does

- Authenticates to a remote host over SSH/SFTP
- Restricts access to the authenticated user's folder under `/data/home`
- Reads connection settings from a local `credentials.json` file
- Shows a folder tree and file table
- Lazily loads subfolders in the tree as they are expanded
- Supports previews for:
  - text-like files such as `.txt`, `.log`, `.csv`, `.json`, `.xml`, `.yaml`, `.py`, `.md`
  - image files such as `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.webp`, `.tif`
  - PDF files when Qt PDF support is available
- Lets users download remote files to their local machine
- Lets users open a selected remote file in the default local application

## Project Layout

```text
main.py                              Main application
credentials.json                     Local connection settings
.venv/                               Local virtual environment
```

## Requirements

- Windows
- Python 3.12
- An SSH/SFTP-accessible server

This project was built in a virtual environment using:

- Python `3.12.7`
- Paramiko `4.0.0`
- PySide6
- PyInstaller `6.19.0`

## Installation

Create and activate a virtual environment, then install the required packages:

## 1. Install virtual environment
```bash
uv venv .venv --python 3.12.7
```
## 🔋 2. Activating the new venv

🍎🐧 **Mac/Linux**
```bash
source .venv/bin/activate
```


🪟 Windows
```bash
.venv\Scripts\activate
```

## 3. Install dependencies
```bash
uv pip install -r requirements.txt
```


**Note:** `pillow` is optional but recommended for faster and lighter image preview processing. Without it, the app will still work but use Qt's image scaling which may be slower.

Depending on your environment, Paramiko may also pull in:

- `cryptography`
- `bcrypt`
- `pynacl`
- `cffi`

## 4. Configuration of the network connection

Connection settings are read from a local `credentials.json` file in the project folder:

```json
{
  "host": "host_ip",
  "port": "port_number"
}
```

Make sure you don't push this file for security reasons, and be cautious about sharing it since it contains connection details.


## 5. Running the App

```bash
python main.py
```

When the app opens:

1. Enter your SSH username and password.
2. The app connects to the configured host.
3. After login, browsing is limited to `/data/home/<username>`.
4. Select files to preview them.
5. Use `Download` to save a remote file locally.
6. Use `Open` to download the file to a temporary location and launch it with the default local app.


## Preview Support

Built-in preview behavior is extension-based:

- Text: `.txt`, `.log`, `.csv`, `.json`, `.xml`, `.yaml`, `.yml`, `.py`, `.m`, `.sh`, `.md`, `.ini`, `.cfg`, `.tsv`
- Images: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.webp`, `.tif`, `.tiff`
- PDFs: `.pdf`

Previews also have lightweight safety limits:

- Text previews read only a limited amount of the file and mark the preview as truncated when needed
- Very large images are not rendered inline
- Very large PDFs are not rendered inline

Unsupported file types can still be downloaded or opened locally.

## Security Notes

- The app is intended to keep users inside their own home folder by normalizing remote paths and validating them against `/data/home/<username>`.
- Credentials are used directly for the SSH connection and are not stored by the app.
- `credentials.json` contains connection details, so it should remain local and should not be shared unnecessarily.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
