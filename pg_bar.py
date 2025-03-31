def run_app(self, app_path):
    if os.name == 'nt':  # Windows
        os.startfile(app_path)
    else:  # Mac/Linux
        os.system(f'open "{app_path}"')


def create_shortcut(self, app_folder_path):
    try:
        app_extension = ".exe" if os.name == 'nt' else ".app"
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        app_path = os.path.join(app_folder_path, f"Vide{app_extension}")
        if os.path.exists(icon_path):
            make_shortcut(app_path, name="Vide", desktop=True, icon=icon_path)
    except Exception as e:
        print(e)



def unzip(self, app_folder_path, create_shortcut_flag, run_flag):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS  # PyInstaller extraction folder
    else:
        base_path = os.path.abspath(".")
    
    app_extension = ".exe" if os.name == 'nt' else ".app"
    source_path = os.path.join(base_path, f"Vide{app_extension}")
    shutil.copy(source_path, f"{app_folder_path}/Vide{app_extension}")

    #Check file size after download
    app_path = os.path.join(app_folder_path, f"Vide{app_extension}")
    file_size = os.path.getsize(app_path)
    
    if create_shortcut_flag:
        self.create_shortcut(app_folder_path)
            
    if run_flag:
        self.run_app(app_path)
    
    self.exit = True

