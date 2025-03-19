import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from pyshortcuts import make_shortcut
import gdown
import threading

def run_app(app_path):
    os.startfile(app_path)

def create_shortcut(app_folder_path):
    try:
        app_path = os.path.join(app_folder_path, "Vide.exe")
        icon_path = os.path.join(app_folder_path, "icon.ico")
        make_shortcut(app_path, name="Vide", desktop=True, icon=icon_path)
        return 1
    except Exception as e:
        print(e)
        return 0
    
def download_with_progress(app_folder_path, create_shortcut_flag, run_flag, progress_bar, status_label):
    try:
        APP_ID = "1_R3T5Tf3GQC08WPNyLQZqYZ4HLViphwG"
        ICON_ID = "1wIIvWh_UAtiabUWQuDQpKHmqFAPGqZwg"
        FILE_URL = "https://drive.google.com/uc?id="
        status_label.config(text="Fetching file info...")
        root.update_idletasks()

        app_url = FILE_URL + APP_ID
        app_path = os.path.join(app_folder_path, "Vide.exe")

        # Download file in chunks
        gdown.download(app_url, app_path, quiet=True, fuzzy=True)

        # Check file size after download
        file_size = os.path.getsize(app_path)
        if file_size > 0:
            if create_shortcut_flag:
                progress_bar["value"] = 80 
            else:
                progress_bar["value"] = 100  # Set progress to 100% on completion
                status_label.config(text="Download Complete ✅")

        if create_shortcut_flag:
            icon_path =  os.path.join(app_folder_path, "icon.ico")

            icon_url = FILE_URL + ICON_ID
            gdown.download(icon_url,  icon_path, quiet=True, fuzzy=True)

            file_size = os.path.getsize(icon_path)
            if file_size > 0:
                    progress_bar["value"] = 100  # Set progress to 100% on completion
                    status_label.config(text="Download Complete ✅")

            if create_shortcut(app_folder_path)!=1:
                messagebox.showerror("Error", "Chortcut creation failed!")  #помилка створення посилання

        if run_flag:
            run_app(app_path)
        
        root.destroy()

    except Exception as e:
        messagebox.showerror("Error", f"Download failed: {str(e)}")

def download_app(app_folder_path, create_shortcut_flag, run_flag):

    progress_bar["value"] = 0
    threading.Thread(target=download_with_progress, args=(app_folder_path, create_shortcut_flag, run_flag, progress_bar, status_label), daemon=True).start()

    
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
        return()
    print(f"Selected Folder: {selected_folder}")
    print(f"Create desktop shortcut: {create_shortcut_flag}")
    print(f"Run app: {run_flag}")

# Create the main window
root = tk.Tk()
root.title("Vide Installer")
root.iconbitmap("./logo.ico")
root.resizable(False, False)

# Create a StringVar to hold the folder path
entry_var = tk.StringVar()

# Entry field to show the selected folder path
entry = tk.Entry(root, textvariable=entry_var, width=50)
entry.grid(row=0, column=0, padx=10, pady=10)

# Button to open folder chooser
btn_browse = tk.Button(root, text="Browse", command=choose_folder)
btn_browse.grid(row=0, column=1, padx=5, pady=10)

# Checkbox for "Create Desktop Shortcut"
checkbox_shortcut_v = tk.BooleanVar()
checkbox_shortcut = tk.Checkbutton(root, text="Create desktop shortcut", variable=checkbox_shortcut_v)
checkbox_shortcut.grid(row=1, column=0, padx=10, pady=10,sticky="w")

checkbox_run_v = tk.BooleanVar()
checkbox_run = tk.Checkbutton(root, text="Run after installation", variable=checkbox_run_v)
checkbox_run.grid(row=2, column=0, padx=10, pady=10,sticky="w")

# Continue button (aligned bottom-right)
btn_continue = tk.Button(root, text="Continue", command=on_continue)
btn_continue.grid(row=3, column=1, padx=10, pady=10, sticky="e")

#instalation progres bar
progress_bar = ttk.Progressbar(root, length=300, mode="determinate")

status_label = tk.Label(root, text="Waiting for download...", fg="blue")

# Run the Tkinter event loop
root.mainloop()

