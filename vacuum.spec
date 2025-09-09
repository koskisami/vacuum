import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE

base_path = os.path.abspath('.')  # current directory


# Include all files from bin/ folder
bin_dir = os.path.join(base_path, "bin")
binaries = []
if os.path.exists(bin_dir):
    for f in os.listdir(bin_dir):
        binaries.append((os.path.join(bin_dir, f), "bin"))

# Include icons
datas = [
    ('icons/icon.ico', 'icons'),   # app icon for EXE
    ('icons/icon.png', 'icons'),   # notification icon
]

hiddenimports = collect_submodules('yt_dlp')  # ensure yt-dlp works

a = Analysis(
    ['vacuum.py'],
    pathex=[base_path],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='vacuum',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/icon.ico',    # executable icon
    onefile=True,             # bundle everything into a single EXE
)
