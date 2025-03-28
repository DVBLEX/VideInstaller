import os
import platform
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pyshortcuts import make_shortcut
import shutil
import sys

if platform.system() == 'Darwin':
    pass


def run_app(app_path):
    if os.name == 'nt':  # Windows
        os.startfile(app_path)
    else:  # Mac/Linux
        os.system(f'open "{app_path}"')


def create_shortcut(app_folder_path):
    try:
        app_extension = ".exe" if os.name == 'nt' else ".app"
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        app_path = os.path.join(app_folder_path, f"Vide{app_extension}")
        if os.path.exists(icon_path):
            make_shortcut(app_path, name="Vide", desktop=True, icon=icon_path)
        return 1
    except Exception as e:
        print(e)
        return 0


def unzip_with_progress(app_folder_path, create_shortcut_flag, run_flag, progress_bar, status_label):
    try:
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
        if file_size > 0:
            if create_shortcut_flag:
                progress_bar["value"] = 80 
            else:
                progress_bar["value"] = 100  # Set progress to 100% on completion
                status_label.config(text="Installation Complete ✅")

        if create_shortcut_flag:
            if create_shortcut(app_folder_path)!=1:
                messagebox.showerror("Error", "Shortcut creation failed!") 
                progress_bar["value"] = 100  # Set progress to 100% on completion
                status_label.config(text="Installation Complete ✅")
            else:
                progress_bar["value"] = 100  # Set progress to 100% on completion
                status_label.config(text="Installation Complete ✅")

        if run_flag:
            run_app(app_path)
        
        root.destroy()

    except Exception as e:
        messagebox.showerror("Error", f"Download failed: {str(e)}")


def download_app(app_folder_path, create_shortcut_flag, run_flag):
    progress_bar["value"] = 0
    threading.Thread(target=unzip_with_progress,
                     args=(app_folder_path, create_shortcut_flag, run_flag, progress_bar, status_label),
                     daemon=True).start()


def choose_folder():
    folder_selected = filedialog.askdirectory(title="Select a folder")
    if folder_selected:
        entry_var.set(folder_selected)  # Set selected folder path in the text field


def next_page():
    entry.grid_forget()
    btn_browse.grid_forget()
    checkbox_shortcut.grid_forget()
    checkbox_run.grid_forget()
    btn_continue.grid_forget()
    select_folder_label.grid_forget()
    progress_bar.grid(row=0, column=0, padx=10, pady=10)
    status_label.grid(row=1, column=0, padx=10, pady=10)


def on_continue():
    selected_folder = entry_var.get()
    create_shortcut_flag = checkbox_shortcut_v.get()
    run_flag = checkbox_run_v.get()
    if os.path.isdir(selected_folder):
        app_folder_path = os.path.join(selected_folder, "Vide")
        os.makedirs(app_folder_path, exist_ok=True)
        next_page()
        download_app(app_folder_path, create_shortcut_flag, run_flag)

    else:
        messagebox.showerror("Error", "Please select folder!")
        return ()
    print(f"Selected Folder: {selected_folder}")
    print(f"Create desktop shortcut: {create_shortcut_flag}")
    print(f"Run app: {run_flag}")

def on_start():
    greetings_label.grid_forget()
    start_btn.grid_forget()
    select_folder_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
    entry.grid(row=1, column=0, padx=10, pady=0)
    btn_browse.grid(row=1, column=1, padx=5, pady=10)
    checkbox_shortcut.grid(row=2, column=0, padx=10, pady=10, sticky="w")
    checkbox_run.grid(row=3, column=0, padx=10, pady=10, sticky="w")
    btn_continue.grid(row=4, column=1, padx=10, pady=10, sticky="e")


if __name__ == "__main__":
    # Create the main window
    root = tk.Tk()
    root.title("Vide Installer")
    root.resizable(False, False)

    # Handle icon loading with proper error handling
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
    try:
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
        else:
            print(f"Warning: Icon file not found at {icon_path}")
    except tk.TclError as e:
        print(f"Warning: Could not load icon: {e}")
    except Exception as e:
        print(f"Warning: Unexpected error loading icon: {e}")


    select_folder_label = tk.Label(root, text="Please select folder :")
    

    # Create a StringVar to hold the folder path
    entry_var = tk.StringVar()


    # Entry field to show the selected folder path
    entry = tk.Entry(root, textvariable=entry_var, width=50)
    

    # Button to open folder chooser
    btn_browse = tk.Button(root, text="Browse", command=choose_folder)
    

    # Checkbox for "Create Desktop Shortcut"
    checkbox_shortcut_v = tk.BooleanVar()
    checkbox_shortcut = tk.Checkbutton(root, text="Create desktop shortcut", variable=checkbox_shortcut_v)
    

    checkbox_run_v = tk.BooleanVar()
    checkbox_run = tk.Checkbutton(root, text="Run after installation", variable=checkbox_run_v)
    
    # Continue button (aligned bottom-right)
    btn_continue = tk.Button(root, text="Continue", command=on_continue)
   
    # installation progress bar
    progress_bar = ttk.Progressbar(root, length=300, mode="determinate")
    
    #Progress bar status label
    status_label = tk.Label(root, text="Waiting for installation...", fg="blue")

    greetings_label = tk.Label(root, text="You are greeted by the Vide installer,\n click the button to proceed with the installation process.",
                               font=12)
    greetings_label.grid(row=2, column=0, padx=10, pady=10)

    start_btn = tk.Button(root, text="Start", command=on_start, width=20)
    start_btn.grid(row=3, column=0, padx=10, pady=10)

    root.mainloop()

