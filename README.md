# Cluster Browser

A Windows desktop SFTP file browser for lab users, built with Python, Paramiko, and PySide6.

Cluster Browser connects to a configured SSH/SFTP server and keeps each user inside their own remote home folder at `/data/home/<username>`. It provides a simple desktop interface for browsing folders, previewing common file types, downloading files, and opening remote files with local applications.

## Highlights

- SSH/SFTP login with a desktop PySide6 interface
- User-scoped browsing under `/data/home/<username>`
- Folder tree with lazy loading for faster navigation
- File table with preview, download, and open actions
- Local `credentials.json` configuration for host and port settings
- Text, image, and PDF preview support with lightweight safety limits

## Preview Support

Preview behavior is extension-based.

| Type | Extensions |
| --- | --- |
| Text | `.txt`, `.log`, `.csv`, `.json`, `.xml`, `.yaml`, `.yml`, `.py`, `.m`, `.sh`, `.md`, `.ini`, `.cfg`, `.tsv` |
| Images | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.webp`, `.tif`, `.tiff` |
| PDFs | `.pdf` |

Unsupported file types can still be downloaded or opened locally.

## Requirements

- Windows
- Python 3.12
- Access to an SSH/SFTP server

Core dependencies are listed in `requirements.txt`:

```text
paramiko
PySide6
pillow
pyinstaller
```

This project was built with Python `3.12.7`. `pillow` is recommended for faster image preview processing.

## Project Layout

```text
.
|-- main.py                  # Main desktop application
|-- requirements.txt         # Python dependencies
|-- credentials.json         # Local connection settings
|-- run_Cluster_Dir_main.bat # Windows launcher
|-- LICENSE                  # MIT License
`-- README.md
```

## Setup

From the project folder, create and activate a virtual environment:

```powershell
uv venv .venv --python 3.12.7
.venv\Scripts\activate
```

Install dependencies:

```powershell
uv pip install -r requirements.txt
```

If you are not using `uv`, the same flow works with standard Python tooling:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Configuration

Connection settings are read from `credentials.json` in the project root:

```json
{
  "host": "host_ip",
  "port": "port_number"
}
```

Keep this file local. It contains connection details and should not be committed or shared unnecessarily.

## Running

Start the app with:

```powershell
python main.py
```

Or use the included launcher:

```powershell
.\run_Cluster_Dir_main.bat
```

When the app opens:

1. Enter your SSH username and password.
2. Connect to the configured host.
3. Browse files inside `/data/home/<username>`.
4. Select a file to preview it.
5. Use `Download` to save a remote file locally.
6. Use `Open` to download a temporary copy and launch it with the default local app.

## Safety Notes

- Remote paths are normalized and validated against `/data/home/<username>`.
- SSH credentials are used for the connection only and are not stored by the app.
- Text previews read only a limited amount of data and mark the preview when truncated.
- Very large images and PDFs are not rendered inline.
- `credentials.json` should remain local because it contains server connection details.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
