# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Y:\\instalki\\_SKRYPTY WIKT\\OgarniaczSM\\build_installer.py'],
    pathex=[],
    binaries=[],
    datas=[('Y:\\instalki\\_SKRYPTY WIKT\\OgarniaczSM\\vc_redist.x64.exe', '.')],
    hiddenimports=[],
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
    name='OgarniaczInstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Y:\\instalki\\_SKRYPTY WIKT\\OgarniaczSM\\icon.ico'],
)
