###Compile Steps###
1. Create a python virtual enviroment
    python -m venv venv
2.  Activate virtual enviroment on Windows
    venv\Scripts\activate
3. Install all the nessesary modules 
    pip install -r requirements.txt
4. Create .exe file for installer
    pyinstaller -F --noconsole --icon=icon.iso installer.py
5. .exe file now is availabe at ./dist/