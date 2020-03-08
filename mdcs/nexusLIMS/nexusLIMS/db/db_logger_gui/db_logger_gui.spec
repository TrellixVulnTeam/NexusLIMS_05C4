# -*- mode: python ; coding: utf-8 -*-
# Run this file with Pyinstaller v3.5, on Python 3.4.4 (32-bit) via:
# C:\Python34-32\Scripts\pyinstaller.exe db_logger_gui.spec

block_cipher = None
options = [ ]

a = Analysis(['db_logger_gui.py'],
             pathex=['Z:\\db'],
             binaries=[],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          options,
          a.binaries + [
              ('logo_bare.png',
              'Z:\\db\\resources\\logo_bare.png',
              'DATA'),
              ('logo_bare_xp.ico',
              'Z:\\db\\resources\\logo_bare_xp.ico',
              'DATA'),
              ('copy.png',
              'Z:\\db\\resources\\copy.png',
              'DATA'),
              ('window-close.png',
              'Z:\\db\\resources\\window-close.png',
              'DATA'),
              ('file.png',
              'Z:\\db\\resources\\file.png',
              'DATA'),
              ('logo_text_250x100.png',
              'Z:\\db\\resources\\logo_text_250x100.png',
              'DATA'),
              ('arrow-alt-circle-right.png',
              'Z:\\db\\resources\\arrow-alt-circle-right.png',
              'DATA'),
              ('arrow-alt-circle-left.png',
              'Z:\\db\\resources\\arrow-alt-circle-left.png',
              'DATA'),
              ('error-icon.png',
              'Z:\\db\\resources\\error-icon.png',
              'DATA'),
              ('file-plus.png',
              'Z:\\db\\resources\\file-plus.png',
              'DATA'),
              ('pause.png',
              'Z:\\db\\resources\\pause.png',
              'DATA'),
              ],
          a.zipfiles,
          a.datas,
          [],
          name='NexusLIMS Session Logger',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          icon='resources\\logo_bare_xp.ico')