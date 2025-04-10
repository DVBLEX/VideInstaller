import PyInstaller.__main__

PyInstaller.__main__.run([
    'installer_qt.py',
    '--windowed',
    '--noconsole',
    '--onefile',
    '--icon=logo.icns',
    '--add-data=dist/Vide.app:.',
    '--add-data=logo.icns:.',
    '--add-data=logo.icns:.',
    '--name=Vide Installer'
])