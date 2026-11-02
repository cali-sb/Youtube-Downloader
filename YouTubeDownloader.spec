# -*- mode: python ; coding: utf-8 -*-

import re
import os
from pathlib import Path

block_cipher = None

# La versión sale de src/version.py; version.txt (recursos del .exe) se genera aquí.
with open('src/version.py', encoding='utf-8') as f:
    APP_VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)
_v = tuple(int(x) for x in (APP_VERSION.split('.') + ['0', '0', '0'])[:4])
with open('version.txt', 'w', encoding='utf-8') as f:
    f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={_v}, prodvers={_v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable(u'040904B0', [
      StringStruct(u'CompanyName', u''),
      StringStruct(u'FileDescription', u'YouTube Downloader'),
      StringStruct(u'FileVersion', u'{APP_VERSION}'),
      StringStruct(u'InternalName', u'YouTubeDownloader'),
      StringStruct(u'ProductName', u'YouTube Downloader'),
      StringStruct(u'ProductVersion', u'{APP_VERSION}')])]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""")

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/qml', 'src/qml'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickControls2',
        'PySide6.QtNetwork',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
        'packaging',
        'mutagen',
        'brotli',
        'Cryptodome',
        'websockets',
        'certifi',
        'requests',
        'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter', 'PIL', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Qt on Windows uses the OS ICU API. PyInstaller can resolve the same DLL name
# from unrelated tools on PATH (e.g. Poppler), which has incompatible exports.
# Leave Windows to supply ICU; FFmpeg's own DLLs remain isolated below.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in ('icuuc.dll', 'icudt78.dll')]

# `excludes` only covers Python modules: PySide6's QML plugins still pull in the
# Chromium that WebEngine embeds. The app never loads it, so don't ship it.
def _is_webengine(entry):
    return re.search(r'webengine|webview', entry[0], re.IGNORECASE) is not None

a.binaries = [entry for entry in a.binaries if not _is_webengine(entry)]
a.datas = [entry for entry in a.datas if not _is_webengine(entry)]

# FFmpeg is a separate process: keep its DLLs away from Qt's DLL search path.
# Append after Analysis so its ICU DLL is not collected into the application root.
ffmpeg_bin = Path('C:/ffmpeg/bin')
for tool in ('ffmpeg.exe', 'ffprobe.exe'):
    if not (ffmpeg_bin / tool).is_file():
        raise FileNotFoundError(ffmpeg_bin / tool)
for tool in [ffmpeg_bin / 'ffmpeg.exe', ffmpeg_bin / 'ffprobe.exe', *ffmpeg_bin.glob('*.dll')]:
    a.datas.append(('ffmpeg/' + tool.name, str(tool), 'DATA'))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YouTubeDownloader',   # nombre fijo: el instalador actualiza en el sitio y no deja .exe viejos
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=os.environ.get('YTD_BUILD_CONSOLE') == '1',
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version.txt',
    icon='assets/icon.ico',
)

COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YouTubeDownloader',
)
