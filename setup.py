
from setuptools import setup

APP = ['installer.py']
DATA_FILES = ['logo.ico']
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'logo.ico',
    'plist': {
        'CFBundleName': "Vide Installer",
        'CFBundleDisplayName': "Vide Installer",
        'CFBundleGetInfoString': "Installing Vide",
        'CFBundleIdentifier': "com.vide.installer",
        'CFBundleVersion': "1.0.0",
        'CFBundleShortVersionString': "1.0.0",
        'NSHumanReadableCopyright': "Copyright © 2025, Vide, All Rights Reserved"
    }
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
