# Compile Steps

## 1. Create a Python virtual environment
```
python -m venv venv
```

## 2.  Activate virtual environment on Windows 
```
venv\Scripts\activate
```
## or MacOS
```
source venv/bin/activate
```

## 3. Install all the necessary modules 
```
pip install -r requirements.txt
```   

## 4. Create an executable file for the installer

### compile installer for Windows:

### compile VM_51 
```
pyinstaller --clean --onefile --noconsole --icon="logo.ico" --name="Vide" VM_51.py
```
### compile VideInstaller
```
pyinstaller --clean --noconsole --onefile --icon="logo.ico" --add-data "dist/Vide.exe;." --add-data "logo.ico;." --add-data "logo.png;." --name="Vide Installer"  installer_qt.py
```

### compile installer for Mac:

### compile VM_51 
```
pyinstaller --clean --noconsole --onefile --icon="logo.icns" --add-data="logo.icns;." --name="Vide" --windowed VM_51.py
or
pyinstaller --clean --noconsole --onefile --icon="logo.icns" --add-data="logo.icns:." --name="Vide" --windowed --collect-all PyQt5 VM_51.py
```
### compile VideInstaller
```
pyinstaller --clean --noconsole --onefile --icon="logo.icns" --add-data "dist/Vide.app:." --add-data "logo.icns:." --add-data "logo.icns:." --name="Vide Installer" --windowed installer_qt.py
```

### for build .dmg or .pkg files:
```
python setup.py py2app
```

### for creating the .dmg file:
```
hdiutil create -volname "Vide Installer" -srcfolder "dist/Vide Installer.app" -ov -format UDZO "dist/Vide_Installer.dmg"
```

### for creating the .pkg file:
```
pyinstaller --clean --noconsole --onefile --icon="logo.icns" --add-data "dist/Vide.app:." --add-data "logo.icns:." --add-data "logo.icns:." --name="Vide Installer" --windowed installer_qt.py
```

```
pkgbuild --component "dist/Vide Installer.app" --install-location "/Applications" --scripts "scripts" --identifier "com.vide.installer" --version "1.0" "dist/Vide_Installer.pkg"
```

5.  .exe or .dmg or .pkg file now is available at ./dist/
