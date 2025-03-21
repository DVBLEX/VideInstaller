#!/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
# -*- coding: utf-8 -*-


import sys, os, subprocess, shutil, logging, re, random
from datetime import datetime
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image, ImageOps
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal

# -----------------------------------------------------------------------------
#                           CONSTANTS & GLOBALS
# -----------------------------------------------------------------------------
DATA_FILE = "event_data.txt"

LOGO_COLOR = "#EC1C5B"
BACKGROUND_COLOR = "#1E1E1E"
BUTTON_COLOR = "#2E2E2E"
HOVER_COLOR = "#3A3A3A"
TEXT_COLOR = "#FFFFFF"
DEEP_PINK = "#EC1C5B"
WHITE = "#FFFFFF"
BLACK = "#000000"

# Only DNP 6x4 mode is supported.
TEMPLATES = {
    "DNP 6x4": {
        "width": 1800,
        "height": 1200,
        "margin_top": 4,
        "margin_left": 4,
        "margin_right": 4,
        "margin_bottom": 12.4,
    },
}

sessions = []
current_template = None

original_paths = {}
manual_crops = {}
manual_crop_rects = {}

NORMAL_RATIO = 4 / 5
used_random_numbers = set()

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename=os.path.join("logs", "vide_maker_improved.log"),
    level=logging.DEBUG,
    format="%(asctime)s:%(levelname)s:%(message)s",
)

# -----------------------------------------------------------------------------
#                           HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def is_image_file(fp):
    return fp.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))

def is_video_file(fp):
    return fp.lower().endswith((".mov", ".mp4", ".avi", ".mkv"))

def extract_number(fname):
    match_custom = re.match(r".*?\b(\d+)\s*\(custom\)", fname, re.IGNORECASE)
    if match_custom:
        return int(match_custom.group(1))
    nums = re.findall(r"(\d+)", fname)
    return int(nums[-1]) if nums else None

def create_output_directory(base_dir, folder_name="output"):
    i = 1
    while True:
        new_dir = os.path.join(base_dir, f"{folder_name} {i}")
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)
            return new_dir
        i += 1

def generate_unique_id():
    today = datetime.now().strftime("%Y%m%d")
    while True:
        rand_val = random.randint(10000, 99999)
        if rand_val not in used_random_numbers:
            used_random_numbers.add(rand_val)
            return f"{today}_{rand_val}"

def get_new_filename(is_photo=True, unique_id=None, copy_num=None):
    if is_photo:
        return f"{unique_id}_p{'_copy' + str(copy_num) if copy_num else ''}.jpg"
    else:
        return f"{unique_id}_v{'_copy' + str(copy_num) if copy_num else ''}.mov"

def crop_to_aspect_ratio(image, ratio=0.8):
    w, h = image.size
    current_ratio = w / h
    if current_ratio > ratio:
        new_w = int(h * ratio)
        left = (w - new_w) // 2
        return image.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / ratio)
        top = (h - new_h) // 2
        return image.crop((0, top, w, top + new_h))

def custom_crop(image, ratio):
    w, h = image.size
    current_ratio = w / h
    if current_ratio > ratio:
        new_w = int(h * ratio)
        left = (w - new_w) // 2
        return image.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / ratio)
        top = (h - new_h) // 2
        return image.crop((0, top, w, top + new_h))

def build_ffmpeg_crop_filter(ratio):
    ratio_str = f"{ratio:.6f}"
    crop_filter = (
        f"crop=if(gt(iw/ih\\,{ratio_str})\\,ih*{ratio_str}\\,iw):"
        f"if(gt(iw/ih\\,{ratio_str})\\,ih\\,iw/{ratio_str}):"
        f"(iw-if(gt(iw/ih\\,{ratio_str})\\,ih*{ratio_str}\\,iw))/2:"
        f"(ih-if(gt(iw/ih\\,{ratio_str})\\,ih\\,iw/{ratio_str}))/2"
    )
    return crop_filter

# --- New sorting key to group duplicate copies together ---
def sort_key_with_copies(filepath):
    base = os.path.splitext(os.path.basename(filepath))[0]
    base_clean = re.sub(r"\s*\(\d+\)$", "", base)
    m = re.search(r"_copy(\d+)", base, re.IGNORECASE)
    if m:
        copy_num = int(m.group(1))
        base_clean = re.sub(r"_copy\d+", "", base, flags=re.IGNORECASE)
    else:
        copy_num = 0
    return (base_clean, copy_num)

# -----------------------------------------------------------------------------
#             FOLDER REORDER & EVENT DATA FUNCTIONS
# -----------------------------------------------------------------------------
def reorder_output_folders(event_folder):
    outs = [f for f in os.listdir(event_folder) if f.startswith("output")]
    outs.sort(key=extract_number)
    exp_normal = 1
    for fold in outs:
        m = re.search(r"(\d+)$", fold)
        if not m:
            continue
        num = int(m.group(1))
        if num != exp_normal:
            old_path = os.path.join(event_folder, fold)
            new_path = os.path.join(event_folder, f"output {exp_normal}")
            os.rename(old_path, new_path)
        exp_normal += 1

def sync_event_from_folders(event_folder, application):
    global sessions, current_template
    sessions.clear()
    data_path = os.path.join(event_folder, DATA_FILE)
    templ_found = False
    if os.path.exists(data_path):
        try:
            with open(data_path, "r") as f:
                lines = f.readlines()
            current_template = lines[0].split(": ")[1].strip()
            templ_found = True
        except:
            pass
    if not templ_found:
        current_template = "DNP 6x4"
    outs = [f for f in os.listdir(event_folder) if f.startswith("output")]
    outs.sort(key=extract_number)
    for idx, fold in enumerate(outs, start=1):
        op = os.path.join(event_folder, fold)
        t_out = os.path.join(op, "template_output")
        tg = len([x for x in os.listdir(op) if is_image_file(os.path.join(op, x))])
        pr = 0
        if os.path.exists(t_out):
            pr = len([x for x in os.listdir(t_out) if is_image_file(os.path.join(t_out, x))])
        sessions.append({
            "folder": op,
            "output": op,
            "targets": tg,
            "prints": pr * 2,
            "print_files": pr,
            "event_digital_folder": os.path.join(event_folder, "digital"),
            "custom": "(custom)" in fold.lower()
        })

def update_event_data(app):
    data_path = os.path.join(app.event_folder, DATA_FILE)
    reorder_output_folders(app.event_folder)
    sync_event_from_folders(app.event_folder, app)
    total_sess = len(sessions)
    total_targets = sum(s["targets"] for s in sessions)
    total_print_files = sum(s["print_files"] for s in sessions)
    total_prints = total_print_files * 2
    with open(data_path, "w") as f:
        f.write(f"Template: {current_template}\n")
        f.write(f"Total Sessions: {total_sess}\n")
        f.write(f"Total Targets: {total_targets}\n")
        f.write(f"Total Prints: {total_prints}\n\n")
        f.write("Sessions Data:\nSession # | Targets | Prints\n")
        for i, se in enumerate(sessions, start=1):
            f.write(f"{i} | {se['targets']} | {se['prints']}\n")

# -----------------------------------------------------------------------------
#                           CREATE PDF & OPEN PRINT DIALOG
# -----------------------------------------------------------------------------
def create_pdf_from_images(folder, pdf_path):
    from PIL import Image
    fs = [os.path.join(folder, x) for x in os.listdir(folder) if is_image_file(os.path.join(folder, x))]
    if not fs:
        return
    fs.sort()
    imgs = [Image.open(fp).convert("RGB") for fp in fs]
    if imgs:
        imgs[0].save(pdf_path, save_all=True, append_images=imgs[1:], quality=100)

def open_print_dialog(folder):
    """Opens the folder for printing by generating a PDF (on Windows) or opening the images sorted by modification date."""
    if os.path.exists(folder):
        items = sorted(
            [os.path.join(folder, f) for f in os.listdir(folder) if is_image_file(os.path.join(folder, f))],
            key=os.path.getmtime
        )
        if items:
            try:
                if sys.platform == "win32":
                    pdf_path = os.path.join(folder, "print_session.pdf")
                    create_pdf_from_images(folder, pdf_path)
                    os.startfile(pdf_path)
                elif sys.platform == "darwin":
                    subprocess.run(["open"] + items)
                else:
                    subprocess.run(["xdg-open"] + items)
            except Exception as e:
                logging.error(f"Print error: {e}")

# -----------------------------------------------------------------------------
#                           PROCESS DIRECTORY FUNCTION
# -----------------------------------------------------------------------------
def process_directory(input_dir, output_dir, progress_callback=None):
    fs = os.listdir(input_dir)
    imgs, vids = [], []
    for f in fs:
        fp = os.path.join(input_dir, f)
        if os.path.isfile(fp):
            if is_image_file(fp):
                imgs.append(f)
            elif is_video_file(fp):
                vids.append(f)
    images_info = [{"file": i, "num": extract_number(i)} for i in imgs]
    videos_info = [{"file": v, "num": extract_number(v)} for v in vids]
    images_info.sort(key=lambda x: x["num"] if x["num"] else float("inf"))
    videos_info.sort(key=lambda x: x["num"] if x["num"] else float("inf"))
    used_videos = set()
    pairs = []
    for i_data in images_info:
        inum = i_data["num"]
        ifile = i_data["file"]
        exact = None
        for v_data in videos_info:
            if v_data["num"] == inum and v_data["file"] not in used_videos:
                exact = v_data
                break
        if exact:
            pairs.append((ifile, exact["file"]))
            used_videos.add(exact["file"])
            continue
        cands = [v for v in videos_info if v["num"] and v["num"] <= inum and v["file"] not in used_videos]
        if cands:
            best = max(cands, key=lambda x: x["num"])
            pairs.append((ifile, best["file"]))
            used_videos.add(best["file"])
            continue
        cands = [v for v in videos_info if v["num"] and v["num"] > inum and v["file"] not in used_videos]
        if cands:
            best = min(cands, key=lambda x: x["num"])
            pairs.append((ifile, best["file"]))
            used_videos.add(best["file"])
            continue
        logging.error(f"No video found for {ifile}")
        raise ValueError(f"No video found for {ifile}")
    total = len(pairs) * 2
    futures = []
    paired_images = []
    done = 0
    with ThreadPoolExecutor() as executor:
        for (img_f, vid_f) in pairs:
            uid = generate_unique_id()
            photo_name = get_new_filename(True, uid)
            paired_images.append(photo_name)
            futures.append(executor.submit(process_file, img_f, "P", uid, input_dir, output_dir))
            futures.append(executor.submit(process_file, vid_f, "V", uid, input_dir, output_dir))
        for i in imgs:
            if "_copy" in i.lower():
                uid = generate_unique_id()
                c_m = re.search(r"_copy(\d+)", i.lower())
                cnum = c_m.group(1) if c_m else "1"
                copy_name = get_new_filename(True, uid, cnum)
                paired_images.append(copy_name)
                futures.append(executor.submit(process_file, i, "P", uid, input_dir, output_dir))
                total += 1
        for future in as_completed(futures):
            try:
                future.result()
                done += 1
                if progress_callback:
                    progress_callback(int((done / total) * 100))
            except Exception as e:
                logging.error(f"process_directory error: {e}")
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                raise
    return paired_images

# -----------------------------------------------------------------------------
#                           APPLY TEMPLATES (WITH OFFSET)
# -----------------------------------------------------------------------------
def apply_templates(photo_paths, template_path, template_out_dir,
                    position_adjustment_mm=0, progress_callback=None,
                    template_name=None):
    from PIL import Image, ImageOps
    global current_template
    if template_name is None:
        template_name = current_template
    tinfo = TEMPLATES[template_name]
    tW, tH = tinfo["width"], tinfo["height"]
    m_top = tinfo["margin_top"]
    m_left = tinfo["margin_left"]
    m_right = tinfo["margin_right"]
    m_bottom = tinfo["margin_bottom"]
    dpi = 300
    px_top = int(m_top * dpi / 25.4)
    px_left = int(m_left * dpi / 25.4)
    px_right = int(m_right * dpi / 25.4)
    px_bottom = int(m_bottom * dpi / 25.4)
    px_adjust = int(position_adjustment_mm * dpi / 25.4)
    template = Image.open(template_path).convert("RGBA")
    final_photos = []
    for p in photo_paths:
        if p in manual_crops:
            final_photos.append(manual_crops[p])
        else:
            final_photos.append(p)
    final_photos.sort(key=sort_key_with_copies)
    def resize_crop(img, w, h):
        ratio_img = img.width / img.height
        ratio_tgt = w / h
        if ratio_img > ratio_tgt:
            sc = h / img.height
        else:
            sc = w / img.width
        new_sz = (int(img.width * sc), int(img.height * sc))
        img = img.resize(new_sz, Image.LANCZOS)
        left = (img.width - w) // 2
        top = (img.height - h) // 2
        return img.crop((left, top, left + w, top + h))
    if len(final_photos) % 2 != 0:
        final_photos.append(final_photos[-1])
    total = len(final_photos)
    for i in range(0, len(final_photos), 2):
        p1 = final_photos[i]
        p2 = final_photos[i+1]
        im1 = Image.open(p1).convert("RGBA")
        im1 = ImageOps.exif_transpose(im1)
        im2 = Image.open(p2).convert("RGBA")
        im2 = ImageOps.exif_transpose(im2)
        half_w = (tW // 2) - px_left - px_right
        av_h = tH - px_top - px_bottom
        r1 = resize_crop(im1, half_w, av_h)
        r2 = resize_crop(im2, half_w, av_h)
        base = Image.new("RGBA", (tW, tH), (255, 255, 255, 255))
        base.paste(template, (0, 0), template)
        base.paste(r1, (px_left, px_top))
        base.paste(template, (tW // 2, 0), template)
        base.paste(r2, ((tW // 2) + px_left, px_top))
        final_width = tW + abs(px_adjust)
        final_img = Image.new("RGBA", (final_width, tH), (255, 255, 255, 255))
        paste_x = px_adjust if px_adjust >= 0 else 0
        final_img.paste(base, (paste_x, 0))
        outp = os.path.join(template_out_dir, f"print_{i // 2}.png")
        final_img.save(outp, dpi=(dpi, dpi), quality=95, subsampling=0)
        if progress_callback:
            prog = int(((i + 2) / total) * 100)
            progress_callback(prog)

# -----------------------------------------------------------------------------
#                           PROCESS FILE FUNCTION
# -----------------------------------------------------------------------------
def process_file(file_name, file_type, unique_id, input_dir, output_dir):
    input_path = os.path.join(input_dir, file_name)
    copy_num_match = re.search(r"_copy(\d+)", file_name.lower())
    copy_num = copy_num_match.group(1) if copy_num_match else None
    is_photo = (file_type.upper() == "P")
    digital_folder = os.path.join(os.path.dirname(output_dir), "digital")
    digi_photos = os.path.join(digital_folder, "photos")
    digi_videos = os.path.join(digital_folder, "videos")
    os.makedirs(digi_photos, exist_ok=True)
    os.makedirs(digi_videos, exist_ok=True)
    if is_photo:
        hr_filename = get_new_filename(True, unique_id, copy_num)
        hr_path = os.path.join(digi_photos, hr_filename)
        try:
            im = Image.open(input_path)
            im = ImageOps.exif_transpose(im)
            auto_crop = crop_to_aspect_ratio(im, NORMAL_RATIO)
            auto_crop.save(hr_path, "JPEG", quality=95, subsampling=0)
            original_paths[hr_path] = input_path
        except Exception as e:
            logging.error(f"Photo HR error: {e}")
            raise
        out_path = os.path.join(output_dir, hr_filename)
        try:
            mini = Image.open(hr_path)
            mini = ImageOps.exif_transpose(mini)
            mini.thumbnail((1200, 1200), Image.LANCZOS)
            mini.save(out_path, "JPEG", quality=85, subsampling=0)
        except Exception as e:
            logging.error(f"Minimize photo error: {e}")
            raise
        return out_path
    else:
        hr_filename = get_new_filename(False, unique_id, copy_num)
        hr_path = os.path.join(digi_videos, hr_filename)
        try:
            shutil.copy(input_path, hr_path)
        except Exception as e:
            logging.error(f"Video copy error: {e}")
            raise
        crop_filter = build_ffmpeg_crop_filter(NORMAL_RATIO)
        out_path = os.path.join(output_dir, hr_filename)
        ffmpeg_cmd = [
            "ffmpeg", "-i", hr_path,
            "-vf", f"{crop_filter},scale=-2:480",
            "-vcodec", "libx264", "-crf", "23", "-preset", "medium",
            "-acodec", "aac",
            out_path
        ]
        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except Exception as e:
            logging.error(f"Video compress error: {e}")
            raise
        return out_path

# -----------------------------------------------------------------------------
#                           WORKER CLASSES
# -----------------------------------------------------------------------------
class Worker(QtCore.QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    show_duplicates_dialog = pyqtSignal(str, list)
    update_sessions = pyqtSignal()
    progress_message = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    process_stopped = pyqtSignal()
    def __init__(self, input_folder, event_folder, template_path, application):
        super().__init__()
        self.input_folder = input_folder
        self.event_folder = event_folder
        self.template_path = template_path
        self.application = application
        self.output_directory = None
        self.paired_images = []
        self.stop_requested = False
    def run(self):
        try:
            self.progress_message.emit("Processing files...")
            self.output_directory = create_output_directory(self.event_folder)
            self.paired_images = process_directory(self.input_folder, self.output_directory, progress_callback=self.update_prog)
            if self.stop_requested:
                self.cleanup()
                return
            self.progress_value.emit(100)
            self.show_duplicates_dialog.emit(self.output_directory, self.paired_images)
        except Exception as e:
            logging.error(f"Worker run error: {e}")
            if self.output_directory and os.path.exists(self.output_directory):
                shutil.rmtree(self.output_directory)
            self.error.emit(str(e))
    def update_prog(self, val):
        self.progress_value.emit(val)
        self.progress_message.emit(f"Processing files... {val}%")
    def update_prog_tmpl(self, val):
        self.progress_value.emit(val)
        self.progress_message.emit(f"Applying templates... {val}%")
    @QtCore.pyqtSlot(dict)
    def process_duplicates(self, duplicates):
        try:
            if self.stop_requested:
                self.cleanup()
                return
            self.progress_value.emit(0)
            for path, count in duplicates.items():
                for i in range(count - 1):
                    cp = os.path.splitext(path)[0] + f"_copy{i+1}" + os.path.splitext(path)[1]
                    shutil.copy(path, cp)
                if self.stop_requested:
                    self.cleanup()
                    return
            if self.template_path:
                template_out = os.path.join(self.output_directory, "template_output")
                os.makedirs(template_out, exist_ok=True)
            else:
                template_out = None
            digi_photos = os.path.join(self.event_folder, "digital", "photos")
            min_photos = [os.path.join(self.output_directory, f)
                          for f in os.listdir(self.output_directory)
                          if is_image_file(os.path.join(self.output_directory, f))]
            normalized = []
            for mp in min_photos:
                dn, fn = os.path.split(mp)
                b, e = os.path.splitext(fn)
                b = re.sub(r"\s*\(\d+\)$", "", b)
                nf = b + e
                np = os.path.join(dn, nf)
                if np != mp:
                    os.rename(mp, np)
                normalized.append(np)
            hr_list = []
            for np in normalized:
                fname = os.path.basename(np)
                hrp = os.path.join(digi_photos, fname)
                if os.path.exists(hrp):
                    hr_list.append(hrp)
                else:
                    hr_list.append(np)
            if template_out:
                self.update_prog_tmpl(0)
                apply_templates(hr_list, self.template_path, template_out,
                                position_adjustment_mm=self.application.template_position_adjustment,
                                progress_callback=self.update_prog_tmpl)
                if self.stop_requested:
                    self.cleanup()
                    return
                if sys.platform == "win32":
                    pdfp = os.path.join(template_out, "print_session.pdf")
                    create_pdf_from_images(template_out, pdfp)
            for f in os.listdir(self.output_directory):
                if "_copy" in f.lower():
                    try:
                        os.remove(os.path.join(self.output_directory, f))
                    except:
                        pass
            if template_out and os.path.exists(template_out):
                prints = len([x for x in os.listdir(template_out) if is_image_file(os.path.join(template_out, x))])
            else:
                prints = 0
            sessions.append({
                "folder": self.input_folder,
                "output": self.output_directory,
                "targets": len(self.paired_images),
                "prints": prints * 2,
                "print_files": prints,
                "event_digital_folder": os.path.join(self.event_folder, "digital"),
                "custom": False
            })
            update_event_data(self.application)
            self.update_sessions.emit()
            self.progress_message.emit("Processing Complete")
            self.finished.emit()
        except Exception as e:
            logging.error(f"Duplicates error: {e}")
            if self.output_directory and os.path.exists(self.output_directory):
                shutil.rmtree(self.output_directory)
            self.error.emit(str(e))
    def cleanup(self):
        if self.output_directory and os.path.exists(self.output_directory):
            shutil.rmtree(self.output_directory)
        self.process_stopped.emit()
    def stop(self):
        self.stop_requested = True

class CustomModeWorker(QtCore.QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    show_duplicates_dialog = pyqtSignal(str, list, float)
    update_sessions = pyqtSignal()
    progress_message = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    process_stopped = pyqtSignal()
    def __init__(self, files, event_folder, minimize, ratio, orientation, template_path, application, apply_template=False, do_crop=True):
        super().__init__()
        self.files = files
        self.event_folder = event_folder
        self.minimize = minimize
        self.ratio = ratio
        self.orientation = orientation
        self.template_path = template_path
        self.application = application
        self.stop_requested = False
        self.output_directory = None
        self.processed_photos = []
        self.processed_videos = []
        self.total_count = len(files)
        self.apply_template = apply_template
        self.do_crop = do_crop
    def run(self):
        try:
            self.progress_message.emit("Processing custom files...")
            custom_dir = os.path.join(self.event_folder, "custom mode")
            os.makedirs(custom_dir, exist_ok=True)
            i = 1
            while True:
                new_dir = os.path.join(custom_dir, f"output {i} (custom)")
                if not os.path.exists(new_dir):
                    os.makedirs(new_dir)
                    self.output_directory = new_dir
                    break
                i += 1
            print_dir = os.path.join(self.output_directory, "print")
            os.makedirs(print_dir, exist_ok=True)
            done = 0
            for f in self.files:
                if self.stop_requested:
                    self.cleanup()
                    return
                uid = generate_unique_id()
                is_photo = is_image_file(f)
                if is_photo:
                    new_photo_name = get_new_filename(True, uid)
                    hi_res_path = os.path.join(print_dir, new_photo_name)
                    try:
                        im = Image.open(f)
                        im = ImageOps.exif_transpose(im)
                    except Exception as e:
                        raise RuntimeError(f"Failed to open image {f}: {e}")
                    if self.do_crop:
                        im = custom_crop(im, self.ratio)
                    try:
                        im.save(hi_res_path, "JPEG", quality=95, subsampling=0)
                        original_paths[hi_res_path] = f
                    except Exception as e:
                        raise RuntimeError(f"Failed to save hi-res for {f}: {e}")
                    out_path = os.path.join(self.output_directory, new_photo_name)
                    if self.minimize:
                        mini = im.copy()
                        mini.thumbnail((1200, 1200), Image.LANCZOS)
                        mini.save(out_path, "JPEG", quality=85, subsampling=0)
                    else:
                        shutil.copy(hi_res_path, out_path)
                    self.processed_photos.append(out_path)
                else:
                    new_video_name = get_new_filename(False, uid)
                    hi_res_path = os.path.join(print_dir, new_video_name)
                    try:
                        shutil.copy(f, hi_res_path)
                    except Exception as e:
                        raise RuntimeError(f"Failed to copy video {f}: {e}")
                    crop_filter = build_ffmpeg_crop_filter(self.ratio)
                    out_path = os.path.join(self.output_directory, new_video_name)
                    ffmpeg_cmd = [
                        "ffmpeg", "-i", hi_res_path,
                        "-vf", f"{crop_filter},scale=-2:480",
                        "-vcodec", "libx264", "-crf", "23", "-preset", "medium",
                        "-acodec", "aac",
                        out_path
                    ]
                    try:
                        subprocess.run(ffmpeg_cmd, check=True)
                    except Exception as e:
                        raise RuntimeError(f"Video compress error {f}: {e}")
                    self.processed_videos.append(out_path)
                done += 1
                pct = int((done / self.total_count) * 100)
                self.progress_value.emit(pct)
                self.progress_message.emit(f"Processing custom files... {pct}%")
            short_names = [os.path.basename(x) for x in self.processed_photos]
            self.show_duplicates_dialog.emit(self.output_directory, short_names, self.ratio)
        except Exception as e:
            logging.error(f"CustomModeWorker run error: {e}")
            if self.output_directory and os.path.exists(self.output_directory):
                shutil.rmtree(self.output_directory)
            self.error.emit(str(e))
    @QtCore.pyqtSlot(dict)
    def process_duplicates(self, duplicates):
        try:
            if self.stop_requested:
                self.cleanup()
                return
            self.progress_value.emit(0)
            for path, count in duplicates.items():
                for i in range(count - 1):
                    cp = os.path.splitext(path)[0] + f"_copy{i+1}" + os.path.splitext(path)[1]
                    shutil.copy(path, cp)
            apply_template = False
            if abs(self.ratio - 0.8) < 1e-3 and self.orientation == "portrait" and self.template_path and self.apply_template:
                apply_template = True
            template_out = None
            if apply_template:
                template_out = os.path.join(self.output_directory, "template_output")
                os.makedirs(template_out, exist_ok=True)
            out_photos = [os.path.join(self.output_directory, f)
                          for f in os.listdir(self.output_directory)
                          if is_image_file(os.path.join(self.output_directory, f))]
            normalized = []
            for mp in out_photos:
                dn, fn = os.path.split(mp)
                b, e = os.path.splitext(fn)
                b = re.sub(r"\s*\(\d+\)$", "", b)
                nf = b + e
                np = os.path.join(dn, nf)
                if np != mp:
                    os.rename(mp, np)
                normalized.append(np)
            print_folder = os.path.join(self.output_directory, "print")
            hr_list = []
            for np in normalized:
                fname = os.path.basename(np)
                hrp = os.path.join(print_folder, fname)
                if os.path.exists(hrp):
                    hr_list.append(hrp)
                else:
                    hr_list.append(np)
            if apply_template:
                def _tmpl_prog(val):
                    self.progress_value.emit(val)
                    self.progress_message.emit(f"Applying templates... {val}%")
                apply_templates(hr_list, self.template_path, template_out,
                                position_adjustment_mm=self.application.template_position_adjustment,
                                progress_callback=_tmpl_prog)
                if sys.platform == "win32":
                    pdfp = os.path.join(template_out, "print_session.pdf")
                    create_pdf_from_images(template_out, pdfp)
            pr_count = 0
            if apply_template and template_out and os.path.exists(template_out):
                pr_count = len([x for x in os.listdir(template_out) if is_image_file(os.path.join(template_out, x))])
            sessions.append({
                "folder": self.output_directory,
                "output": self.output_directory,
                "targets": self.total_count,
                "prints": pr_count * 2,
                "print_files": pr_count,
                "event_digital_folder": os.path.join(self.event_folder, "digital"),
                "custom": True
            })
            update_event_data(self.application)
            self.update_sessions.emit()
            self.progress_message.emit("Custom Processing Complete")
            self.finished.emit()
            if sys.platform == "win32":
                os.startfile(self.output_directory)
            elif sys.platform == "darwin":
                subprocess.run(["open", self.output_directory])
            else:
                subprocess.run(["xdg-open", self.output_directory])
        except Exception as e:
            logging.error(f"CustomModeWorker duplicates error: {e}")
            if self.output_directory and os.path.exists(self.output_directory):
                shutil.rmtree(self.output_directory)
            self.error.emit(str(e))
    def cleanup(self):
        if self.output_directory and os.path.exists(self.output_directory):
            shutil.rmtree(self.output_directory)
        self.process_stopped.emit()
    def stop(self):
        self.stop_requested = True

# -----------------------------------------------------------------------------
#                           UI CLASSES
# -----------------------------------------------------------------------------
class ClickableLabel(QtWidgets.QLabel):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
    def mousePressEvent(self, event):
        dlg = ImagePreview(self.path)
        dlg.exec_()

class ImagePreview(QtWidgets.QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Preview")
        self.setModal(True)
        self.path = path
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        scr = QtWidgets.QApplication.desktop().availableGeometry()
        self.resize(scr.width(), scr.height())
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(50,50,50,50)
        bg = QtWidgets.QLabel()
        bg.setStyleSheet("background-color: rgba(0,0,0,180);")
        main_layout.addWidget(bg)
        big_lbl = QtWidgets.QLabel()
        pm = QtGui.QPixmap(self.path).scaled(scr.width()-100, scr.height()-100,
                                              QtCore.Qt.KeepAspectRatio,
                                              QtCore.Qt.SmoothTransformation)
        big_lbl.setPixmap(pm)
        big_lbl.setAlignment(QtCore.Qt.AlignCenter)
        big_lbl.setStyleSheet("background-color: transparent;")
        main_layout.addWidget(big_lbl, 0, QtCore.Qt.AlignCenter)
        close_btn = QtWidgets.QPushButton("X")
        close_btn.setFixedSize(40,40)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,200);
                color: black;
                border-radius: 20px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: rgba(200,200,200,200);
            }
        """)
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn, 0, QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
    def mousePressEvent(self, event):
        self.close()

class DuplicatesDialog(QtWidgets.QDialog):
    def __init__(self, parent, output_directory, paired_images, ratio=NORMAL_RATIO):
        super().__init__(parent)
        self.setWindowTitle("Duplicates & Crop Editor")
        self.setModal(True)
        self.resize(1000,600)
        self.output_directory = output_directory
        self.paired_images = paired_images
        self.duplicates = {}
        self.ratio = ratio
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(20)
        lbl = QtWidgets.QLabel("Set duplicates or edit/refresh crop for each photo:")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(lbl)
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(content)
        self.grid_layout.setAlignment(QtCore.Qt.AlignCenter)
        self.grid_layout.setSpacing(20)
        self.populate_grid()
        scroll_area.setWidget(content)
        main_layout.addWidget(scroll_area)
        setall_h = QtWidgets.QHBoxLayout()
        la = QtWidgets.QLabel("Set # copies for all images:")
        setall_h.addWidget(la)
        self.set_all_spin = QtWidgets.QSpinBox()
        self.set_all_spin.setMinimum(1)
        self.set_all_spin.setValue(1)
        self.set_all_spin.setAlignment(QtCore.Qt.AlignCenter)
        setall_h.addWidget(self.set_all_spin)
        setall_btn = QtWidgets.QPushButton("Set All")
        setall_btn.clicked.connect(self.set_all_copies)
        setall_h.addWidget(setall_btn)
        main_layout.addLayout(setall_h)
        btns = QtWidgets.QHBoxLayout()
        okb = QtWidgets.QPushButton("OK")
        okb.clicked.connect(self.accept)
        canc = QtWidgets.QPushButton("Cancel")
        canc.clicked.connect(self.reject)
        btns.addWidget(okb)
        btns.addWidget(canc)
        main_layout.addLayout(btns)
    def populate_grid(self):
        row = 0
        col = 0
        max_cols = 4
        for img_name in self.paired_images:
            path = os.path.join(self.output_directory, img_name)
            if not os.path.exists(path):
                continue
            pm = QtGui.QPixmap(path).scaled(150,150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            lbl = ClickableLabel(path)
            lbl.setPixmap(pm)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            sp = QtWidgets.QSpinBox()
            sp.setMinimum(1)
            sp.setValue(1)
            sp.setAlignment(QtCore.Qt.AlignCenter)
            edit_btn = QtWidgets.QPushButton("Edit")
            edit_btn.clicked.connect(partial(self.open_crop_editor, path, lbl))
            refresh_btn = QtWidgets.QPushButton()
            ref_icon = self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload)
            refresh_btn.setIcon(ref_icon)
            refresh_btn.clicked.connect(partial(self.refresh_crop, path, lbl))
            vlay = QtWidgets.QVBoxLayout()
            vlay.addWidget(lbl)
            hh = QtWidgets.QHBoxLayout()
            hh.addWidget(edit_btn)
            hh.addWidget(refresh_btn)
            vlay.addLayout(hh)
            vlay.addWidget(sp)
            container = QtWidgets.QWidget()
            container.setLayout(vlay)
            self.grid_layout.addWidget(container, row, col)
            self.duplicates[path] = sp
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
    def open_crop_editor(self, photo_path, label_widget):
        dlg = CropEditorDialog(photo_path, ratio=self.ratio, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            pm = QtGui.QPixmap(photo_path).scaled(150,150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            label_widget.setPixmap(pm)
    def refresh_crop(self, photo_path, label_widget):
        if photo_path in manual_crops:
            manp = manual_crops[photo_path]
            if os.path.exists(manp):
                os.remove(manp)
            del manual_crops[photo_path]
        if photo_path in manual_crop_rects:
            del manual_crop_rects[photo_path]
        base_out = re.sub(r"_copy\d+", "", os.path.basename(photo_path), flags=re.IGNORECASE)
        digi_hr = None
        for dig, bp in original_paths.items():
            if os.path.basename(dig) == base_out:
                digi_hr = dig
                break
        if not digi_hr:
            digi_hr = photo_path
        try:
            hi_img = Image.open(digi_hr)
            hi_img = ImageOps.exif_transpose(hi_img)
            if abs(self.ratio - NORMAL_RATIO) < 1e-5:
                ac = crop_to_aspect_ratio(hi_img, NORMAL_RATIO)
            else:
                ac = custom_crop(hi_img, self.ratio)
            ac.thumbnail((1200,1200), Image.LANCZOS)
            ac.save(photo_path, "JPEG", quality=85)
        except Exception as e:
            logging.error(f"Refresh error: {e}")
        pm = QtGui.QPixmap(photo_path).scaled(150,150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        label_widget.setPixmap(pm)
    def set_all_copies(self):
        val = self.set_all_spin.value()
        for spb in self.duplicates.values():
            spb.setValue(val)
    def get_duplicates(self):
        d = {}
        for path, spin_box in self.duplicates.items():
            d[path] = spin_box.value()
        return d

class CropRatioDialog(QtWidgets.QDialog):
    def __init__(self, current_ratio, current_orientation, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop Ratio")
        self.current_ratio = current_ratio
        self.current_orientation = current_orientation
        self.ratio_map = {
            "1:1": 1.0,
            "16:9": 16/9,
            "4:5": 4/5,
            "5:7": 5/7,
            "4:3": 4/3,
            "2:5": 2/5,
            "3:2": 3/2
        }
        layout = QtWidgets.QVBoxLayout(self)
        hl = QtWidgets.QHBoxLayout()
        self.combo_ratio = QtWidgets.QComboBox()
        self.combo_ratio.addItems(self.ratio_map.keys())
        initial_key = None
        for k, v in self.ratio_map.items():
            if abs(v - self.current_ratio) < 1e-5:
                initial_key = k
                break
        if initial_key is None:
            initial_key = "4:5"
        self.combo_ratio.setCurrentText(initial_key)
        hl.addWidget(QtWidgets.QLabel("Ratio:"))
        hl.addWidget(self.combo_ratio)
        layout.addLayout(hl)
        or_layout = QtWidgets.QHBoxLayout()
        or_layout.addWidget(QtWidgets.QLabel("Orientation:"))
        self.radio_portrait = QtWidgets.QRadioButton("Portrait")
        self.radio_landscape = QtWidgets.QRadioButton("Landscape")
        or_layout.addWidget(self.radio_portrait)
        or_layout.addWidget(self.radio_landscape)
        layout.addLayout(or_layout)
        if self.current_orientation == "landscape":
            self.radio_landscape.setChecked(True)
        else:
            self.radio_portrait.setChecked(True)
        self.check_ratio_one_to_one()
        self.combo_ratio.currentTextChanged.connect(self.on_ratio_changed)
        btns = QtWidgets.QHBoxLayout()
        ok_b = QtWidgets.QPushButton("OK")
        ok_b.clicked.connect(self.accept)
        ca_b = QtWidgets.QPushButton("Cancel")
        ca_b.clicked.connect(self.reject)
        btns.addWidget(ok_b)
        btns.addWidget(ca_b)
        layout.addLayout(btns)
    def on_ratio_changed(self, txt):
        val = self.ratio_map[txt]
        if abs(val - 1.0) < 1e-5:
            self.radio_portrait.setEnabled(False)
            self.radio_landscape.setEnabled(False)
        else:
            self.radio_portrait.setEnabled(True)
            self.radio_landscape.setEnabled(True)
    def check_ratio_one_to_one(self):
        if abs(self.current_ratio - 1.0) < 1e-5:
            self.radio_portrait.setEnabled(False)
            self.radio_landscape.setEnabled(False)
        else:
            self.radio_portrait.setEnabled(True)
            self.radio_landscape.setEnabled(True)
    def get_ratio_orientation(self):
        chosen_key = self.combo_ratio.currentText()
        val = self.ratio_map[chosen_key]
        if self.radio_portrait.isChecked():
            if val > 1:
                val = 1.0 / val
            orientation = "portrait"
        else:
            if val < 1:
                val = 1.0 / val
            orientation = "landscape"
        return val, orientation

class CropEditorDialog(QtWidgets.QDialog):
    def __init__(self, output_photo_path, ratio=0.8, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop Editor")
        self.resize(600,450)
        self.output_photo_path = output_photo_path
        self.ratio = ratio
        base_out = re.sub(r"_copy\d+", "", os.path.basename(output_photo_path), flags=re.IGNORECASE)
        self.digital_hr_path = None
        self.original_browse_path = None
        for dig, bp in original_paths.items():
            if os.path.basename(dig) == base_out:
                self.digital_hr_path = dig
                self.original_browse_path = bp
                break
        if not self.digital_hr_path:
            self.digital_hr_path = output_photo_path
            self.original_browse_path = output_photo_path
        from io import BytesIO
        try:
            pil_img = Image.open(self.original_browse_path)
            pil_img = ImageOps.exif_transpose(pil_img)
        except:
            pil_img = Image.open(self.output_photo_path)
        self.orig_w, self.orig_h = pil_img.size
        buf = BytesIO()
        pil_img.save(buf, format="JPEG")
        buf.seek(0)
        data = buf.read()
        pm = QtGui.QPixmap()
        pm.loadFromData(data)
        pm = pm.scaled(600,400, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.displayed_w = pm.width()
        self.displayed_h = pm.height()
        init_rect = None
        if self.output_photo_path in manual_crop_rects:
            saved = manual_crop_rects[self.output_photo_path]
            x, y, w, h, ow, oh = saved
            scale_x = self.displayed_w / float(ow)
            scale_y = self.displayed_h / float(oh)
            new_x = int(x * scale_x)
            new_y = int(y * scale_y)
            new_w = int(w * scale_x)
            new_h = int(h * scale_y)
            init_rect = QtCore.QRect(new_x, new_y, new_w, new_h)
        self.crop_label = RubberBandCropWidget(pm, ratio=self.ratio, initial_rect=init_rect, parent=self)
        self.crop_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.btn_reset = QtWidgets.QPushButton("Reset")
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_apply = QtWidgets.QPushButton("Apply Crop")
        self.btn_apply.clicked.connect(self.on_apply)
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(self.btn_reset)
        hl.addWidget(self.btn_apply)
        hl.addWidget(self.btn_cancel)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.crop_label)
        layout.addLayout(hl)
    def on_reset(self):
        if self.output_photo_path in manual_crops:
            mp = manual_crops[self.output_photo_path]
            if os.path.exists(mp):
                os.remove(mp)
            del manual_crops[self.output_photo_path]
        if self.output_photo_path in manual_crop_rects:
            del manual_crop_rects[self.output_photo_path]
        base_out = re.sub(r"_copy\d+", "", os.path.basename(self.output_photo_path), flags=re.IGNORECASE)
        digi_hr = None
        for dig, bp in original_paths.items():
            if os.path.basename(dig) == base_out:
                digi_hr = dig
                break
        if not digi_hr:
            digi_hr = self.output_photo_path
        try:
            im = Image.open(digi_hr)
            im = ImageOps.exif_transpose(im)
            if abs(self.ratio - NORMAL_RATIO) < 1e-5:
                auto_c = crop_to_aspect_ratio(im, NORMAL_RATIO)
            else:
                auto_c = custom_crop(im, self.ratio)
            auto_c.thumbnail((1200,1200), Image.LANCZOS)
            auto_c.save(self.output_photo_path, "JPEG", quality=85)
        except Exception as e:
            logging.error(f"Reset error: {e}")
        pix = self.crop_label.pixmap()
        if pix:
            self.crop_label.cropRect = self.crop_label.get_default_crop_rect(pix.width(), pix.height())
            self.crop_label.update()
    def on_apply(self):
        from PIL import Image
        if not self.crop_label.pixmap():
            return
        scale_x = self.orig_w / float(self.displayed_w)
        scale_y = self.orig_h / float(self.displayed_h)
        x = int(self.crop_label.cropRect.left() * scale_x)
        y = int(self.crop_label.cropRect.top() * scale_y)
        w = int(self.crop_label.cropRect.width() * scale_x)
        h = int(self.crop_label.cropRect.height() * scale_y)
        try:
            big_img = Image.open(self.original_browse_path)
            big_img = ImageOps.exif_transpose(big_img)
        except:
            big_img = Image.open(self.output_photo_path)
        ow, oh = big_img.size
        if x < 0: x = 0
        if y < 0: y = 0
        if x + w > ow: w = ow - x
        if y + h > oh: h = oh - y
        c = big_img.crop((x, y, x + w, y + h))
        c.save(self.output_photo_path, "JPEG", quality=95)
        c2 = c.copy()
        c2.thumbnail((1200,1200), Image.LANCZOS)
        c2.save(self.output_photo_path, "JPEG", quality=85)
        manual_crops[self.output_photo_path] = self.output_photo_path
        manual_crops[self.digital_hr_path] = self.output_photo_path
        manual_crop_rects[self.output_photo_path] = (x, y, w, h, ow, oh)
        self.accept()

class RubberBandCropWidget(QtWidgets.QLabel):
    def __init__(self, pixmap, ratio=0.8, initial_rect=None, parent=None):
        super().__init__(parent)
        self.setPixmap(pixmap)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.ratio = ratio
        self.dragging = False
        self.resizing = False
        self.resizeHandleSize = 20
        self.resizeCorner = None
        self.dragOffset = None
        if initial_rect:
            self.cropRect = initial_rect
        else:
            self.cropRect = self.get_default_crop_rect(pixmap.width(), pixmap.height())
        self.setMouseTracking(True)
    def get_default_crop_rect(self, img_w, img_h):
        if (img_w / img_h) > self.ratio:
            new_w = int(img_h * self.ratio)
            new_h = img_h
            x = (img_w - new_w) // 2
            y = 0
        else:
            new_w = img_w
            new_h = int(img_w / self.ratio)
            x = 0
            y = (img_h - new_h) // 2
        return QtCore.QRect(x, y, new_w, new_h)
    def updateCropRect(self, rect):
        pix = self.pixmap()
        if not pix:
            return
        img_w = pix.width()
        img_h = pix.height()
        if rect.left() < 0:
            rect.moveLeft(0)
        if rect.top() < 0:
            rect.moveTop(0)
        if rect.right() > img_w:
            rect.moveRight(img_w)
        if rect.bottom() > img_h:
            rect.moveBottom(img_h)
        w = rect.width()
        h = rect.height()
        if w < 1: w = 1
        if h < 1: h = 1
        current_ratio = w / h
        if current_ratio > self.ratio:
            w = int(h * self.ratio)
        else:
            h = int(w / self.ratio)
        new_rect = QtCore.QRect(rect.topLeft(), QtCore.QSize(w, h))
        if new_rect.right() > img_w:
            new_rect.moveRight(img_w)
        if new_rect.bottom() > img_h:
            new_rect.moveBottom(img_h)
        if new_rect.left() < 0:
            new_rect.moveLeft(0)
        if new_rect.top() < 0:
            new_rect.moveTop(0)
        self.cropRect = new_rect
        self.update()
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(DEEP_PINK), 2)
        painter.setPen(pen)
        if not self.pixmap():
            return
        pix = self.pixmap()
        label_w = self.width()
        label_h = self.height()
        pix_w = pix.width()
        pix_h = pix.height()
        scale = min(label_w / pix_w, label_h / pix_h)
        offset_x = (label_w - pix_w * scale) / 2
        offset_y = (label_h - pix_h * scale) / 2
        scaledRect = QtCore.QRectF(
            offset_x + self.cropRect.left() * scale,
            offset_y + self.cropRect.top() * scale,
            self.cropRect.width() * scale,
            self.cropRect.height() * scale
        )
        painter.drawRect(scaledRect)
        handle_size = 6
        for point in [self.cropRect.topLeft(), self.cropRect.topRight(), self.cropRect.bottomLeft(), self.cropRect.bottomRight()]:
            scaled_point = QtCore.QPointF(offset_x + point.x() * scale, offset_y + point.y() * scale)
            rect_handle = QtCore.QRectF(scaled_point.x() - handle_size/2, scaled_point.y() - handle_size/2, handle_size, handle_size)
            painter.fillRect(rect_handle, QtGui.QColor(DEEP_PINK))
    def mousePressEvent(self, event):
        if not self.pixmap():
            return
        if event.button() == QtCore.Qt.LeftButton:
            label_x = event.x()
            label_y = event.y()
            pix = self.pixmap()
            label_w = self.width()
            label_h = self.height()
            pix_w = pix.width()
            pix_h = pix.height()
            scale = min(label_w / pix_w, label_h / pix_h)
            offset_x = (label_w - pix_w * scale) / 2
            offset_y = (label_h - pix_h * scale) / 2
            img_x = (label_x - offset_x) / scale
            img_y = (label_y - offset_y) / scale
            pos = QtCore.QPoint(int(img_x), int(img_y))
            corners = {
                "tl": self.cropRect.topLeft(),
                "tr": self.cropRect.topRight(),
                "bl": self.cropRect.bottomLeft(),
                "br": self.cropRect.bottomRight()
            }
            for key, corner in corners.items():
                if (pos - corner).manhattanLength() <= self.resizeHandleSize:
                    self.resizing = True
                    self.resizeCorner = key
                    self.fixedPoint = None
                    if key == "tl":
                        self.fixedPoint = self.cropRect.bottomRight()
                    elif key == "tr":
                        self.fixedPoint = self.cropRect.bottomLeft()
                    elif key == "bl":
                        self.fixedPoint = self.cropRect.topRight()
                    elif key == "br":
                        self.fixedPoint = self.cropRect.topLeft()
                    event.accept()
                    return
            self.dragging = True
            self.dragOffset = pos - self.cropRect.topLeft()
            event.accept()
    def mouseMoveEvent(self, event):
        if not self.pixmap():
            return
        label_x = event.x()
        label_y = event.y()
        pix = self.pixmap()
        label_w = self.width()
        label_h = self.height()
        pix_w = pix.width()
        pix_h = pix.height()
        scale = min(label_w / pix_w, label_h / pix_h)
        offset_x = (label_w - pix_w * scale) / 2
        offset_y = (label_h - pix_h * scale) / 2
        img_x = (label_x - offset_x) / scale
        img_y = (label_y - offset_y) / scale
        pos = QtCore.QPoint(int(img_x), int(img_y))
        if self.resizing and hasattr(self, "fixedPoint") and self.fixedPoint is not None:
            if self.resizeCorner == "tl":
                dx = self.fixedPoint.x() - pos.x()
                dy = self.fixedPoint.y() - pos.y()
                if dx / self.ratio > dy:
                    new_height = dy
                    new_width = int(self.ratio * new_height)
                else:
                    new_width = dx
                    new_height = int(new_width / self.ratio)
                new_top_left = QtCore.QPoint(self.fixedPoint.x() - new_width, self.fixedPoint.y() - new_height)
                newRect = QtCore.QRect(new_top_left, self.fixedPoint)
            elif self.resizeCorner == "tr":
                dx = pos.x() - self.fixedPoint.x()
                dy = self.fixedPoint.y() - pos.y()
                if dx / self.ratio > dy:
                    new_height = dy
                    new_width = int(self.ratio * new_height)
                else:
                    new_width = dx
                    new_height = int(new_width / self.ratio)
                new_top_right = QtCore.QPoint(self.fixedPoint.x() + new_width, self.fixedPoint.y() - new_height)
                newRect = QtCore.QRect(QtCore.QPoint(self.fixedPoint.x(), self.fixedPoint.y() - new_height),
                                       QtCore.QSize(new_width, new_height))
                newRect.moveLeft(self.fixedPoint.x() - new_width)
            elif self.resizeCorner == "bl":
                dx = self.fixedPoint.x() - pos.x()
                dy = pos.y() - self.fixedPoint.y()
                if dx / self.ratio > dy:
                    new_height = dy
                    new_width = int(self.ratio * new_height)
                else:
                    new_width = dx
                    new_height = int(new_width / self.ratio)
                new_bottom_left = QtCore.QPoint(self.fixedPoint.x() - new_width, self.fixedPoint.y() + new_height)
                newRect = QtCore.QRect(self.fixedPoint, new_bottom_left).normalized()
            elif self.resizeCorner == "br":
                dx = pos.x() - self.fixedPoint.x()
                dy = pos.y() - self.fixedPoint.y()
                if dx / self.ratio > dy:
                    new_height = dy
                    new_width = int(self.ratio * new_height)
                else:
                    new_width = dx
                    new_height = int(new_width / self.ratio)
                new_bottom_right = QtCore.QPoint(self.fixedPoint.x() + new_width, self.fixedPoint.y() + new_height)
                newRect = QtCore.QRect(self.fixedPoint, new_bottom_right)
            else:
                newRect = self.cropRect
            if newRect.left() < 0:
                newRect.moveLeft(0)
            if newRect.top() < 0:
                newRect.moveTop(0)
            if newRect.right() > pix_w:
                newRect.moveRight(pix_w)
            if newRect.bottom() > pix_h:
                newRect.moveBottom(pix_h)
            self.cropRect = newRect
            self.update()
            event.accept()
            return
        if self.dragging:
            new_top_left = pos - self.dragOffset
            newRect = QtCore.QRect(new_top_left, self.cropRect.size())
            self.updateCropRect(newRect)
            event.accept()
            return
        corners = {
            "tl": self.cropRect.topLeft(),
            "tr": self.cropRect.topRight(),
            "bl": self.cropRect.bottomLeft(),
            "br": self.cropRect.bottomRight()
        }
        cursor_set = False
        for key, corner in corners.items():
            if (pos - corner).manhattanLength() <= self.resizeHandleSize:
                if key in ["tl", "br"]:
                    self.setCursor(QtCore.Qt.SizeFDiagCursor)
                else:
                    self.setCursor(QtCore.Qt.SizeBDiagCursor)
                cursor_set = True
                break
        if not cursor_set:
            self.setCursor(QtCore.Qt.ArrowCursor)
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resizeCorner = None
        event.accept()

# -----------------------------------------------------------------------------
#                           PrintSelectionDialog CLASS
# -----------------------------------------------------------------------------
class PrintSelectionDialog(QtWidgets.QDialog):
    def __init__(self, parent, output_folder, template_path):
        super().__init__(parent)
        self.setWindowTitle("Select Photos to Print")
        self.setModal(True)
        self.resize(800,600)
        self.output_folder = output_folder
        self.template_path = template_path
        self.photo_widgets = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(20)
        instr = QtWidgets.QLabel("Select photos & how many copies to print:")
        instr.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(instr)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        scr_content = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(scr_content)
        self.grid.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.setSpacing(20)
        self.populate_grid()
        self.scroll_area.setWidget(scr_content)
        layout.addWidget(self.scroll_area)
        btn_h = QtWidgets.QHBoxLayout()
        pr_btn = QtWidgets.QPushButton("Print")
        pr_btn.clicked.connect(self.accept)
        ca_btn = QtWidgets.QPushButton("Cancel")
        ca_btn.clicked.connect(self.reject)
        btn_h.addWidget(pr_btn)
        btn_h.addWidget(ca_btn)
        layout.addLayout(btn_h)
    def populate_grid(self):
        row = 0
        col = 0
        max_col = 3
        fs = [f for f in os.listdir(self.output_folder) if is_image_file(os.path.join(self.output_folder, f))]
        for i, imgf in enumerate(fs):
            path = os.path.join(self.output_folder, imgf)
            pm = QtGui.QPixmap(path).scaled(150,150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            lbl = QtWidgets.QLabel()
            lbl.setPixmap(pm)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            check = QtWidgets.QCheckBox("Select")
            spin_box = QtWidgets.QSpinBox()
            spin_box.setMinimum(1)
            spin_box.setValue(1)
            spin_box.setAlignment(QtCore.Qt.AlignCenter)
            spin_box.setEnabled(False)
            def togg(state, sb=spin_box):
                sb.setEnabled(state == QtCore.Qt.Checked)
            check.stateChanged.connect(togg)
            self.grid.addWidget(lbl, row, col)
            self.grid.addWidget(check, row+1, col)
            self.grid.addWidget(spin_box, row+2, col)
            self.photo_widgets.append((check, spin_box, path))
            col += 1
            if col >= max_col:
                col = 0
                row += 3
    def get_selected_photos(self):
        chosen = []
        copies_dict = {}
        for cb, sp, path in self.photo_widgets:
            if cb.isChecked():
                chosen.append(path)
                copies_dict[path] = sp.value()
        return chosen, copies_dict

# -----------------------------------------------------------------------------
#                           CUSTOM MODE DIALOG CLASS
# -----------------------------------------------------------------------------
class CustomModeDialog(QtWidgets.QDialog):
    duplicates_ready = pyqtSignal(dict)
    def __init__(self, application, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Mode")
        self.application = application
        self.files = []
        if not hasattr(application, 'last_custom_ratio'):
            application.last_custom_ratio = NORMAL_RATIO
            application.last_custom_orientation = "portrait"
        self.ratio = application.last_custom_ratio
        self.orientation = application.last_custom_orientation
        self.minimize = False
        self.template_path = None
        self.apply_template = False
        self.enable_crop = True
        self.resize(600,400)
        main_layout = QtWidgets.QVBoxLayout(self)
        self.file_list = QtWidgets.QListWidget()
        main_layout.addWidget(self.file_list)
        btns_layout = QtWidgets.QHBoxLayout()
        self.btn_add_files = QtWidgets.QPushButton("Add Files")
        self.btn_add_files.clicked.connect(self.on_add_files)
        btns_layout.addWidget(self.btn_add_files)
        self.btn_delete_file = QtWidgets.QPushButton("Delete File")
        self.btn_delete_file.clicked.connect(self.on_delete_file)
        btns_layout.addWidget(self.btn_delete_file)
        self.check_minimize = QtWidgets.QCheckBox("Minimize")
        btns_layout.addWidget(self.check_minimize)
        self.btn_crop_ratio = QtWidgets.QPushButton("Crop Ratio")
        self.btn_crop_ratio.clicked.connect(self.on_crop_ratio)
        btns_layout.addWidget(self.btn_crop_ratio)
        self.crop_toggle = QtWidgets.QCheckBox("Enable Crop")
        self.crop_toggle.setChecked(True)
        btns_layout.addWidget(self.crop_toggle)
        self.check_template = QtWidgets.QCheckBox("Template")
        self.check_template.setChecked(False)
        self.check_template.setEnabled(False)
        btns_layout.addWidget(self.check_template)
        main_layout.addLayout(btns_layout)
        self.progress_label = QtWidgets.QLabel("")
        main_layout.addWidget(self.progress_label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
                background-color:{BUTTON_COLOR};
            }}
            QProgressBar::chunk {{
                background-color:{DEEP_PINK};
                width:20px;
            }}
        """)
        main_layout.addWidget(self.progress_bar)
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_start.clicked.connect(self.on_start)
        main_layout.addWidget(self.btn_start)
        self.worker_thread = None
        self.worker = None
        self.update_template_button_state()
    def on_add_files(self):
        dlg = QtWidgets.QFileDialog(self, "Select Files", os.path.expanduser("~/Downloads"))
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
        dlg.setNameFilter("Images/Videos (*.png *.jpg *.jpeg *.bmp *.gif *.mov *.mp4 *.avi *.mkv)")
        if dlg.exec_():
            selected = dlg.selectedFiles()
            for s in selected:
                self.files.append(s)
                self.file_list.addItem(s)
    def on_delete_file(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select file(s) to delete.")
            return
        for item in selected_items:
            file_path = item.text()
            if file_path in self.files:
                self.files.remove(file_path)
            self.file_list.takeItem(self.file_list.row(item))
    def on_crop_ratio(self):
        dlg = CropRatioDialog(self.ratio, self.orientation, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.ratio, self.orientation = dlg.get_ratio_orientation()
            self.application.last_custom_ratio = self.ratio
            self.application.last_custom_orientation = self.orientation
        self.update_template_button_state()
    def update_template_button_state(self):
        if (abs(self.ratio - 0.8) < 1e-5 and self.orientation == "portrait" and self.application.template_path):
            self.check_template.setEnabled(True)
        else:
            self.check_template.setEnabled(False)
            self.check_template.setChecked(False)
    def on_start(self):
        if not self.files:
            QtWidgets.QMessageBox.warning(self, "No Files", "Please add some files first.")
            return
        self.minimize = self.check_minimize.isChecked()
        self.apply_template = self.check_template.isChecked()
        self.enable_crop = self.crop_toggle.isChecked()
        if not self.enable_crop and not self.minimize:
            QtWidgets.QMessageBox.warning(self, "No Crop/Minimize Selected", "Please enable crop or minimize.")
            return
        if self.apply_template and not self.application.template_path:
            QtWidgets.QMessageBox.warning(self, "No Template", "Template is toggled ON but no template file is found.")
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.progress_label.setText("Starting...")
        self.btn_start.setEnabled(False)
        self.btn_add_files.setEnabled(False)
        self.btn_delete_file.setEnabled(False)
        self.btn_crop_ratio.setEnabled(False)
        self.check_template.setEnabled(False)
        self.check_minimize.setEnabled(False)
        self.crop_toggle.setEnabled(False)
        self.worker_thread = QtCore.QThread()
        self.worker = CustomModeWorker(
            self.files,
            self.application.event_folder,
            self.check_minimize.isChecked(),
            self.ratio,
            self.orientation,
            self.application.template_path,
            self.application,
            apply_template=self.apply_template,
            do_crop=self.enable_crop
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.error.connect(self.on_worker_error)
        self.worker.show_duplicates_dialog.connect(self.on_show_duplicates_dialog)
        self.worker.update_sessions.connect(self.application.update_sessions_signal.emit)
        self.worker.finished.connect(self.on_processing_complete)
        self.worker.progress_message.connect(self.update_progress_label)
        self.worker.progress_value.connect(self.update_progress_bar)
        self.worker.process_stopped.connect(self.on_process_stopped)
        self.duplicates_ready.connect(self.worker.process_duplicates)
        self.worker_thread.start()
    def on_worker_error(self, msg):
        self.application.error_signal.emit("Error", msg)
        self.close()
    def on_show_duplicates_dialog(self, out_dir, photos, ratio):
        dlg = DuplicatesDialog(self.application, out_dir, photos, ratio=ratio)
        r = dlg.exec_()
        if r == QtWidgets.QDialog.Accepted:
            dups = dlg.get_duplicates()
            self.duplicates_ready.emit(dups)
        else:
            self.worker.stop()
    def on_processing_complete(self):
        self.progress_label.setText("Custom Processing Complete")
        self.progress_bar.setVisible(False)
        self.application.message_signal.emit("Done", "Custom mode processing complete.")
        self.close()
    def update_progress_label(self, msg):
        self.progress_label.setText(msg)
    def update_progress_bar(self, val):
        self.progress_bar.setValue(val)
    def on_process_stopped(self):
        self.close()
    def update_progress_value(self, val):
        if not self.progress_bar.isVisible():
            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(val)

# -----------------------------------------------------------------------------
#                           APPLICATION CLASS
# -----------------------------------------------------------------------------
class Application(QtWidgets.QMainWindow):
    error_signal = pyqtSignal(str, str)
    message_signal = pyqtSignal(str, str)
    update_sessions_signal = pyqtSignal()
    processing_complete_signal = pyqtSignal()
    show_duplicates_dialog_signal = pyqtSignal(str, list)
    duplicates_ready = pyqtSignal(dict)
    progress_message_signal = pyqtSignal(str)
    progress_value_signal = QtCore.pyqtSignal(int)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vide")
        self.setup_palette()
        self.template_path = None
        self.event_folder = None
        self.input_folder = None
        self.worker_thread = None
        self.worker = None
        self.template_position_adjustment = 0
        self.proceed_without_template = False
        self.setup_ui()
        self.connect_signals()
        self.setMinimumSize(500,500)
        self.resize(800,1000)
        self.show()
    def setup_palette(self):
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(BACKGROUND_COLOR))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_COLOR))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(BUTTON_COLOR))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(BUTTON_COLOR))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(TEXT_COLOR))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TEXT_COLOR))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_COLOR))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor(BUTTON_COLOR))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_COLOR))
        pal.setColor(QtGui.QPalette.BrightText, QtGui.QColor(DEEP_PINK))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(DEEP_PINK))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(TEXT_COLOR))
        self.setPalette(pal)
        self.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    def connect_signals(self):
        self.error_signal.connect(self.show_custom_error)
        self.message_signal.connect(self.show_custom_message)
        self.update_sessions_signal.connect(self.update_sessions_table)
        self.processing_complete_signal.connect(self.processing_complete)
        self.show_duplicates_dialog_signal.connect(self.on_show_duplicates_dialog)
        self.progress_message_signal.connect(self.update_progress_message)
        self.progress_value_signal.connect(self.update_progress_value)
    def setup_ui(self):
        font = QtGui.QFont("Helvetica Neue", 12)
        self.setFont(font)
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10,10,10,10)
        main_layout.setSpacing(10)
        self.stack = QtWidgets.QStackedWidget()
        main_layout.addWidget(self.stack)
        self.screen1 = QtWidgets.QWidget()
        self.setup_screen1_ui()
        self.stack.addWidget(self.screen1)
        self.screen2 = QtWidgets.QWidget()
        self.setup_screen2_ui()
        self.stack.addWidget(self.screen2)
        self.stack.setCurrentWidget(self.screen1)
    def setup_screen1_ui(self):
        layout = QtWidgets.QVBoxLayout(self.screen1)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.setSpacing(20)
        logo_lbl = QtWidgets.QLabel()
        px = QtGui.QPixmap("logo.png")
        if not px.isNull():
            px = px.scaled(200,100, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            logo_lbl.setPixmap(px)
        logo_lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(logo_lbl)
        self.event_name_edit = QtWidgets.QLineEdit()
        self.event_name_edit.setPlaceholderText("Enter event name")
        self.event_name_edit.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR}; background-color:{BUTTON_COLOR}; border:1px solid {TEXT_COLOR}; padding:6px; border-radius:5px;")
        layout.addWidget(self.event_name_edit)
        self.event_date_edit = QtWidgets.QLineEdit()
        self.event_date_edit.setPlaceholderText("YYYY-MM-DD")
        self.event_date_edit.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR}; background-color:{BUTTON_COLOR}; border:1px solid {TEXT_COLOR}; padding:6px; border-radius:5px;")
        self.event_date_edit.setText(datetime.now().strftime("%Y-%m-%d"))
        layout.addWidget(self.event_date_edit)
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.addItems(list(TEMPLATES.keys()))
        self.template_combo.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR}; background-color:{BUTTON_COLOR}; border:1px solid {TEXT_COLOR}; padding:6px; border-radius:5px;")
        layout.addWidget(self.template_combo)
        create_btn = QtWidgets.QPushButton("Create Event")
        create_btn.setStyleSheet(f"""
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        create_btn.clicked.connect(self.create_event_folder)
        layout.addWidget(create_btn)
        or_label = QtWidgets.QLabel("OR")
        or_label.setAlignment(QtCore.Qt.AlignCenter)
        or_label.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR};")
        layout.addWidget(or_label)
        open_btn = QtWidgets.QPushButton("Open Existing Event")
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        open_btn.clicked.connect(self.open_existing_event)
        layout.addWidget(open_btn)
    def setup_screen2_ui(self):
        layout = QtWidgets.QVBoxLayout(self.screen2)
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.setSpacing(20)
        logo_lbl = QtWidgets.QLabel()
        px = QtGui.QPixmap("logo.png")
        if not px.isNull():
            px = px.scaled(200,100, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            logo_lbl.setPixmap(px)
        logo_lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(logo_lbl)
        template_group = QtWidgets.QGroupBox("Upload Template")
        template_group.setStyleSheet(f"""
            QGroupBox {{
                font-size:12px;
                color:{TEXT_COLOR};
                border:1px solid {TEXT_COLOR};
                margin-top:20px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding:6px;
            }}
        """)
        tg_layout = QtWidgets.QVBoxLayout(template_group)
        self.template_button = QtWidgets.QPushButton("Upload Template")
        self.template_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.template_button.clicked.connect(self.upload_template)
        tg_layout.addWidget(self.template_button)
        layout.addWidget(template_group)
        folder_group = QtWidgets.QGroupBox("Choose Folder")
        folder_group.setStyleSheet(f"""
            QGroupBox {{
                font-size:12px;
                color:{TEXT_COLOR};
                border:1px solid {TEXT_COLOR};
                margin-top:20px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding:6px;
            }}
        """)
        fg_layout = QtWidgets.QHBoxLayout(folder_group)
        self.folder_line_edit = QtWidgets.QLineEdit()
        self.folder_line_edit.setPlaceholderText("Select folder containing photos & videos")
        self.folder_line_edit.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR}; background-color:{BUTTON_COLOR}; border:1px solid {TEXT_COLOR}; padding:6px; border-radius:5px;")
        fg_layout.addWidget(self.folder_line_edit)
        self.folder_button = QtWidgets.QPushButton("Browse")
        self.folder_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.folder_button.clicked.connect(self.browse_folder)
        fg_layout.addWidget(self.folder_button)
        layout.addWidget(folder_group)
        self.start_button = QtWidgets.QPushButton("Start Vide Maker")
        self.start_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:10px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.start_button.clicked.connect(self.start_processing)
        layout.addWidget(self.start_button)
        self.stop_button = QtWidgets.QPushButton("Stop Processing")
        self.stop_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:10px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self.stop_processing)
        layout.addWidget(self.stop_button)
        self.custom_mode_button = QtWidgets.QPushButton("Custom Mode")
        self.custom_mode_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:10px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.custom_mode_button.clicked.connect(self.open_custom_mode)
        layout.addWidget(self.custom_mode_button)
        sessions_container = QtWidgets.QWidget()
        sessions_layout = QtWidgets.QVBoxLayout(sessions_container)
        sessions_layout.setContentsMargins(0,0,0,0)
        sessions_layout.setSpacing(0)
        self.sessions_table = QtWidgets.QTableWidget()
        self.sessions_table.setColumnCount(7)
        self.sessions_table.setHorizontalHeaderLabels(["Session #", "Targets", "Prints", "Open Folder", "Print All", "Print Selected", "Delete"])
        self.sessions_table.horizontalHeader().setStretchLastSection(True)
        self.sessions_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.sessions_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.sessions_table.verticalHeader().setDefaultSectionSize(35)
        self.sessions_table.setStyleSheet(f"""
            QHeaderView::section {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                padding:5px;
                border:none;
                font-weight:bold;
            }}
            QTableWidget {{
                gridline-color:{BUTTON_COLOR};
                font-size:12px;
                color:{TEXT_COLOR};
                background-color:{BUTTON_COLOR};
            }}
            QTableView::item {{
                border:none;
                padding:10px;
            }}
            QPushButton {{
                background-color:transparent;
                border:none;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.sessions_table.setMaximumHeight(500)
        sessions_layout.addWidget(self.sessions_table)
        layout.addWidget(sessions_container)
        self.loading_label = QtWidgets.QLabel("")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self.loading_label.setStyleSheet(f"color:{TEXT_COLOR}; font-size:12px;")
        layout.addWidget(self.loading_label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
                background-color:{BUTTON_COLOR};
            }}
            QProgressBar::chunk {{
                background-color:{DEEP_PINK};
                width:20px;
            }}
        """)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(20)
        self.summary_label = QtWidgets.QLabel("Total Targets: 0 | Total Prints: 0")
        self.summary_label.setAlignment(QtCore.Qt.AlignCenter)
        self.summary_label.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR};")
        layout.addWidget(self.summary_label)
        btn_layout = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.refresh_button.clicked.connect(self.refresh_application)
        btn_layout.addWidget(self.refresh_button)
        self.end_event_button = QtWidgets.QPushButton("End Event")
        self.end_event_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        self.end_event_button.clicked.connect(lambda: copy_files_to_digital_folder(self))
        btn_layout.addWidget(self.end_event_button)
        settings_btn = QtWidgets.QPushButton("Settings")
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        settings_btn.clicked.connect(self.open_settings)
        btn_layout.addWidget(settings_btn)
        layout.addLayout(btn_layout)
    def create_event_folder(self):
        en = self.event_name_edit.text()
        ed = self.event_date_edit.text()
        if not en or not ed:
            self.error_signal.emit("Error", "Please enter event name & date.")
            return
        folder_name = f"{en}_{ed}"
        self.event_folder = os.path.join(os.path.expanduser("~/Downloads"), folder_name)
        os.makedirs(self.event_folder, exist_ok=True)
        global current_template
        current_template = self.template_combo.currentText()
        with open(os.path.join(self.event_folder, DATA_FILE), "w") as f:
            f.write(f"Template: {current_template}\n")
        self.message_signal.emit("Event Created", "Event folder created.")
        self.stack.setCurrentWidget(self.screen2)
    def open_existing_event(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Event Folder", os.path.expanduser("~/Downloads"))
        if d:
            self.event_folder = d
            sync_event_from_folders(d, self)
            self.update_sessions_table()
            tfs = [x for x in os.listdir(d) if is_image_file(os.path.join(d, x))]
            if tfs:
                self.template_path = os.path.join(d, tfs[0])
            else:
                self.template_path = None
            self.stack.setCurrentWidget(self.screen2)
    def upload_template(self):
        if not self.event_folder:
            self.error_signal.emit("Error", "Please create/open an event first.")
            return
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Template", os.path.expanduser("~/Downloads"), "Image Files (*.png *.jpg *.jpeg)")
        if fp:
            self.template_path = fp
            shutil.copy(fp, os.path.join(self.event_folder, os.path.basename(fp)))
            self.message_signal.emit("Template Uploaded", "Template uploaded successfully.")
    def browse_folder(self):
        f = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Input Folder", os.path.expanduser("~/Downloads"))
        if f:
            self.input_folder = f
            self.folder_line_edit.setText(f)
    def start_processing(self):
        if not self.event_folder:
            self.error_signal.emit("Error", "Please create an event first.")
            return
        if not self.input_folder:
            self.error_signal.emit("Error", "Please select a folder.")
            return
        self.proceed_without_template = False
        if not self.template_path:
            ans = QtWidgets.QMessageBox(self)
            ans.setWindowTitle("No Template Selected")
            ans.setText("No template found. Do you want to upload one or continue without?")
            upload_btn = ans.addButton("Upload Template", QtWidgets.QMessageBox.ActionRole)
            continue_btn = ans.addButton("Continue Without", QtWidgets.QMessageBox.ActionRole)
            ans.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            ans.exec_()
            if ans.clickedButton() == upload_btn:
                self.upload_template()
                if not self.template_path:
                    return
            elif ans.clickedButton() == continue_btn:
                self.proceed_without_template = True
            else:
                return
        self.loading_label.setText("Processing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.start_button.setVisible(False)
        self.stop_button.setVisible(True)
        self.custom_mode_button.setEnabled(False)
        self.worker_thread = QtCore.QThread()
        self.worker = Worker(self.input_folder, self.event_folder, self.template_path, self)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.error.connect(self.on_worker_error)
        self.worker.show_duplicates_dialog.connect(self.on_show_duplicates_dialog)
        self.worker.update_sessions.connect(self.update_sessions_signal.emit)
        self.worker.finished.connect(self.processing_complete_signal.emit)
        self.worker.progress_message.connect(self.update_progress_message)
        self.worker.progress_value.connect(self.update_progress_value)
        self.worker.process_stopped.connect(self.process_stopped)
        self.duplicates_ready.connect(self.worker.process_duplicates)
        self.worker_thread.start()
    def stop_processing(self):
        ans = QtWidgets.QMessageBox.question(self, "Stop Process", "Are you sure? This deletes partial data.", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ans == QtWidgets.QMessageBox.Yes:
            if self.worker:
                self.worker.stop()
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.delete_current_session()
    def delete_current_session(self):
        self.input_folder = None
        self.folder_line_edit.clear()
        self.loading_label.setText("")
        self.progress_bar.setVisible(False)
        self.start_button.setVisible(True)
        self.stop_button.setVisible(False)
        self.custom_mode_button.setEnabled(True)
        self.message_signal.emit("Process Stopped", "Session removed.")
        self.refresh_application()
    def process_stopped(self):
        self.start_button.setVisible(True)
        self.stop_button.setVisible(False)
        self.custom_mode_button.setEnabled(True)
    def on_worker_error(self, msg):
        self.error_signal.emit("Error", msg)
        self.reset_progress()
        self.refresh_application()
    def on_show_duplicates_dialog(self, out_dir, paired_imgs):
        dlg = DuplicatesDialog(self, out_dir, paired_imgs, ratio=NORMAL_RATIO)
        r = dlg.exec_()
        if r == QtWidgets.QDialog.Accepted:
            dups = dlg.get_duplicates()
            self.duplicates_ready.emit(dups)
        else:
            self.worker.stop()
    def processing_complete(self):
        self.loading_label.setText("Complete")
        self.reset_progress()
        self.update_sessions_table()
        self.message_signal.emit("Processing Complete", "All done.")
        self.start_button.setVisible(True)
        self.stop_button.setVisible(False)
        self.custom_mode_button.setEnabled(True)
    def reset_progress(self):
        self.progress_bar.setVisible(False)
        self.loading_label.setText("")
    def update_progress_message(self, msg):
        self.loading_label.setText(msg)
    def update_progress_value(self, val):
        if not self.progress_bar.isVisible():
            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(val)
    def update_sessions_table(self):
        self.sessions_table.setRowCount(0)
        total_targets = 0
        total_prints = 0
        for idx, sn in enumerate(sessions, start=1):
            out_f = sn["output"]
            tg = sn["targets"]
            pr = sn["prints"]
            total_targets += tg
            total_prints += pr
            row = self.sessions_table.rowCount()
            self.sessions_table.insertRow(row)
            session_item = QtWidgets.QTableWidgetItem(f"Session {idx}" + (" (custom)" if sn.get("custom", False) else ""))
            session_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.sessions_table.setItem(row, 0, session_item)
            targets_item = QtWidgets.QTableWidgetItem(str(tg))
            targets_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.sessions_table.setItem(row, 1, targets_item)
            prints_item = QtWidgets.QTableWidgetItem(str(pr))
            prints_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.sessions_table.setItem(row, 2, prints_item)
            open_btn = QtWidgets.QPushButton()
            ic = self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon)
            open_btn.setIcon(ic)
            open_btn.setStyleSheet("background-color: transparent; border: none;")
            open_btn.clicked.connect(partial(self.open_folder, idx - 1))
            self.sessions_table.setCellWidget(row, 3, open_btn)
            pr_ico = QtGui.QIcon.fromTheme("document-print")
            if pr_ico.isNull():
                pr_ico = self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView)
            print_all_btn = QtWidgets.QPushButton()
            print_all_btn.setIcon(pr_ico)
            print_all_btn.setStyleSheet("background-color: transparent; border: none;")
            print_all_btn.setToolTip("Print All")
            if sn["prints"] == 0:
                print_all_btn.setEnabled(False)
            print_all_btn.clicked.connect(partial(self.print_session, idx - 1))
            self.sessions_table.setCellWidget(row, 4, print_all_btn)
            print_sel_btn = QtWidgets.QPushButton()
            print_sel_btn.setIcon(pr_ico)
            print_sel_btn.setStyleSheet("background-color: transparent; border: none;")
            print_sel_btn.setToolTip("Print Selected")
            if sn["prints"] == 0:
                print_sel_btn.setEnabled(False)
            print_sel_btn.clicked.connect(partial(self.print_selected_photos, idx - 1))
            self.sessions_table.setCellWidget(row, 5, print_sel_btn)
            del_btn = QtWidgets.QPushButton()
            trash_icon = self.style().standardIcon(QtWidgets.QStyle.SP_TrashIcon)
            del_btn.setIcon(trash_icon)
            del_btn.setStyleSheet("background-color: transparent; border: none;")
            del_btn.clicked.connect(partial(self.delete_session, idx - 1))
            self.sessions_table.setCellWidget(row, 6, del_btn)
        self.summary_label.setText(f"Total Targets: {total_targets} | Total Prints: {total_prints}")
        sb = self.sessions_table.verticalScrollBar()
        sb.setValue(sb.maximum())
    def open_folder(self, idx):
        out_f = sessions[idx]["output"]
        if os.path.exists(out_f):
            if sys.platform == "win32":
                os.startfile(out_f)
            elif sys.platform == "darwin":
                subprocess.run(["open", out_f])
            else:
                subprocess.run(["xdg-open", out_f])
    def print_session(self, idx):
        out_f = sessions[idx]["output"]
        t_out = os.path.join(out_f, "template_output")
        open_print_dialog(t_out)
    def print_selected_photos(self, idx):
        out_f = sessions[idx]["output"]
        dlg = PrintSelectionDialog(self, out_f, self.template_path)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            chosen_photos, copies_dict = dlg.get_selected_photos()
            if chosen_photos:
                new_dir = self.create_template_output_folder(out_f)
                self.apply_template_to_selected_photos(chosen_photos, copies_dict, new_dir)
                open_print_dialog(new_dir)
            else:
                QtWidgets.QMessageBox.warning(self, "No Selection", "No photos were selected.")
    def create_template_output_folder(self, outf):
        i = 1
        while True:
            nd = os.path.join(outf, f"template_output({i})")
            if not os.path.exists(nd):
                os.makedirs(nd)
                return nd
            i += 1
    def apply_template_to_selected_photos(self, selected_photos, copies_dict, tmpl_out):
        digi_photos = os.path.join(self.event_folder, "digital", "photos")
        photos_paths = []
        for p in selected_photos:
            c = copies_dict[p]
            for i in range(c):
                if c > 1:
                    base, ext = os.path.splitext(os.path.basename(p))
                    copy_name = f"{base}_copy{i+1}{ext}"
                    cp = os.path.join(os.path.dirname(p), copy_name)
                    shutil.copy(p, cp)
                    photos_paths.append(cp)
                else:
                    photos_paths.append(p)
        normalized = []
        for path in photos_paths:
            dn, fn = os.path.split(path)
            b, e = os.path.splitext(fn)
            b = re.sub(r"\s*\(\d+\)$", "", b)
            nf = b + e
            np = os.path.join(dn, nf)
            if np != path:
                os.rename(path, np)
            normalized.append(np)
        hr_list = []
        for np in normalized:
            fname = os.path.basename(np)
            hrp = os.path.join(digi_photos, fname)
            if os.path.exists(hrp):
                hr_list.append(hrp)
            else:
                hr_list.append(np)
        apply_templates(hr_list, self.template_path, tmpl_out,
                        position_adjustment_mm=self.template_position_adjustment,
                        template_name=current_template)
        for x in photos_paths:
            if "_copy" in os.path.basename(x).lower():
                try:
                    os.remove(x)
                except:
                    pass
    def delete_session(self, idx):
        ans = QtWidgets.QMessageBox.question(self, "Delete Session", "Are you sure?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ans == QtWidgets.QMessageBox.Yes:
            s = sessions[idx]
            out_f = s["output"]
            if os.path.exists(out_f):
                try:
                    shutil.rmtree(out_f)
                except:
                    pass
            del sessions[idx]
            update_event_data(self)
            self.update_sessions_table()
    def open_custom_mode(self):
        if not self.event_folder:
            self.error_signal.emit("Error", "Please create or open an event first.")
            return
        dlg = CustomModeDialog(self)
        dlg.exec_()
        self.update_sessions_table()
    def open_settings(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setModal(True)
        dlg.setStyleSheet(f"background-color:{BACKGROUND_COLOR}; color:{TEXT_COLOR};")
        l = QtWidgets.QVBoxLayout(dlg)
        lab = QtWidgets.QLabel("Adjust Template Position (±2.5 mm):")
        lab.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR};")
        l.addWidget(lab)
        hh = QtWidgets.QHBoxLayout()
        left_b = QtWidgets.QPushButton("<")
        left_b.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
                min-width:40px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        left_b.clicked.connect(self.decrease_adjust)
        hh.addWidget(left_b)
        self.adjust_label = QtWidgets.QLabel(f"{self.template_position_adjustment} mm")
        self.adjust_label.setAlignment(QtCore.Qt.AlignCenter)
        self.adjust_label.setStyleSheet(f"font-size:12px; color:{TEXT_COLOR};")
        hh.addWidget(self.adjust_label)
        right_b = QtWidgets.QPushButton(">")
        right_b.setStyleSheet(f"""
            QPushButton {{
                background-color:{BUTTON_COLOR};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border:1px solid {TEXT_COLOR};
                border-radius:5px;
                min-width:40px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        right_b.clicked.connect(self.increase_adjust)
        hh.addWidget(right_b)
        l.addLayout(hh)
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{TEXT_COLOR};
                font-size:12px;
                padding:6px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        save_btn.clicked.connect(lambda: self.save_settings(dlg))
        l.addWidget(save_btn)
        dlg.exec_()
    def decrease_adjust(self):
        if self.template_position_adjustment > -2.5:
            self.template_position_adjustment -= 0.5
            self.adjust_label.setText(f"{self.template_position_adjustment} mm")
    def increase_adjust(self):
        if self.template_position_adjustment < 2.5:
            self.template_position_adjustment += 0.5
            self.adjust_label.setText(f"{self.template_position_adjustment} mm")
    def save_settings(self, dlg):
        global template_position_adjustment
        template_position_adjustment = self.template_position_adjustment
        logging.info(f"Template position => {template_position_adjustment} mm")
        self.message_signal.emit("Settings Saved", "Template position updated.")
        dlg.accept()
    def refresh_application(self):
        self.input_folder = None
        self.folder_line_edit.clear()
        if self.event_folder and self.template_path:
            self.template_path = os.path.join(self.event_folder, os.path.basename(self.template_path))
        self.loading_label.setText("")
        self.progress_bar.setVisible(False)
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self.stop_button.setEnabled(False)
        self.message_signal.emit("Refreshed", "Ready to go.")
        self.update_sessions_table()
    def show_custom_error(self, title, msg):
        mb = QtWidgets.QMessageBox(self)
        mb.setIcon(QtWidgets.QMessageBox.Critical)
        mb.setWindowTitle(title)
        mb.setText(msg)
        mb.setStyleSheet(f"""
            QMessageBox {{
                background-color:{BLACK};
                color:{WHITE};
            }}
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{WHITE};
                padding:6px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        mb.exec_()
        self.reset_progress()
    def show_custom_message(self, title, msg):
        mb = QtWidgets.QMessageBox(self)
        mb.setIcon(QtWidgets.QMessageBox.Information)
        mb.setWindowTitle(title)
        mb.setText(msg)
        mb.setStyleSheet(f"""
            QMessageBox {{
                background-color:{BLACK};
                color:{WHITE};
            }}
            QPushButton {{
                background-color:{DEEP_PINK};
                color:{WHITE};
                padding:6px;
                border-radius:5px;
            }}
            QPushButton:hover {{
                background-color:{HOVER_COLOR};
            }}
        """)
        mb.exec_()
    def closeEvent(self, event):
        ans = QtWidgets.QMessageBox.question(self, "Quit?", "Do you want to quit?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ans == QtWidgets.QMessageBox.Yes:
            event.accept()
            sys.exit()
        else:
            event.ignore()

# -----------------------------------------------------------------------------
#                                   MAIN
# -----------------------------------------------------------------------------
def create_virtual_environment():
    venv = os.path.join(os.getcwd(), "venv")
    pyexe = sys.executable
    if not os.path.isdir(venv):
        print("Creating venv..")
        subprocess.check_call([pyexe, "-m", "venv", "venv"])
        activate_and_install_packages(venv)
        vpy = os.path.join(venv, "Scripts", "python") if os.name == "nt" else os.path.join(venv, "bin", "python")
        print("Restarting script under venv python..")
        os.execv(vpy, [vpy] + sys.argv)
    else:
        try:
            from PyQt5 import QtCore, QtGui, QtWidgets
            from PIL import Image
        except ImportError:
            activate_and_install_packages(venv)
            vpy = os.path.join(venv, "Scripts", "python") if os.name == "nt" else os.path.join(venv, "bin", "python")
            os.execv(vpy, [vpy] + sys.argv)

def activate_and_install_packages(venv):
    pip_exe = os.path.join(venv, "Scripts", "pip") if os.name == "nt" else os.path.join(venv, "bin", "pip")
    subprocess.check_call([pip_exe, "install", "PyQt5", "Pillow"])

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = Application()
    sys.exit(app.exec_())
