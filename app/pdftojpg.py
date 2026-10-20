#!/usr/bin/env python3
"""
Multi-function utility script:
- PDF to JPG conversion
- Scanner integration (Brother ADS-1600W)
"""

import os
import math
import shutil
import subprocess
import datetime
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageStat
import win32com.client
import io

# PIL's default limit is ~178MP (178956970 pixels) for decompression bomb protection
# We'll calculate appropriate DPI to stay within this limit
PIL_MAX_PIXELS = 178_956_970


def show_function_menu():
    """Show a custom window to select which function to use."""
    
    result = None

    def on_pdf_to_jpg():
        nonlocal result
        result = "pdf_to_jpg"
        root.destroy()

    def on_scan():
        nonlocal result
        result = "scan"
        root.destroy()

    root = tk.Tk()
    root.title("pdfmagican")
    
    # Center the window
    root.withdraw() # Hide window while building it
    root.attributes('-topmost', True)

    main_frame = tk.Frame(root, padx=20, pady=20)
    main_frame.pack(expand=True, fill=tk.BOTH)

    label = tk.Label(main_frame, text="What would you like to do?", font=("Segoe UI", 12))
    label.pack(pady=(0, 20))

    btn_frame = tk.Frame(main_frame)
    btn_frame.pack()

    pdf_btn = tk.Button(btn_frame, text="PDF to JPG", command=on_pdf_to_jpg, width=25, height=2, font=("Segoe UI", 10))
    pdf_btn.pack(side=tk.LEFT, padx=10)

    scan_btn = tk.Button(btn_frame, text="Scan with office scanner", command=on_scan, width=25, height=2, font=("Segoe UI", 10))
    scan_btn.pack(side=tk.LEFT, padx=10)

    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    root.geometry('%dx%d+%d+%d' % (w, h, x, y))
    root.deiconify() # Show window now that it's centered

    root.mainloop()
    
    return result


def is_blank(img: Image.Image, threshold=5, white_perc=0.98) -> bool:
    """
    Check if an image is likely blank.
    It's blank if it's almost entirely one color (e.g., white) and has low standard deviation.
    """
    # Convert to grayscale for simplicity
    gs_img = img.convert('L')
    
    # Get histogram of pixel values
    hist = gs_img.histogram()
    
    # Check if most pixels are white (255) or near-white
    total_pixels = gs_img.width * gs_img.height
    
    # Sum pixels from 250-255
    near_white_pixels = sum(hist[250:])
    if (near_white_pixels / total_pixels) > white_perc:
        # Check if there's any significant content (low std dev)
        stat = ImageStat.Stat(gs_img)
        if stat.stddev[0] < threshold:
            print(f"    Blank detected: stddev={stat.stddev[0]:.2f} < {threshold}, white_perc={(near_white_pixels / total_pixels)*100:.1f}% > {white_perc*100:.1f}%")
            return True

    return False

def resize_if_needed(img: Image.Image, max_size: int = 8000, max_mp: int = 24) -> Image.Image:
    """Resize image if longer side exceeds max_size or total resolution exceeds max_mp, maintaining aspect ratio."""
    width, height = img.size
    total_pixels = width * height
    max_pixels = max_mp * 1_000_000  # Convert megapixels to pixels
    
    # Calculate scale factors for both constraints
    scale_longer_side = 1.0
    scale_total_res = 1.0
    
    longer_side = max(width, height)
    if longer_side > max_size:
        scale_longer_side = max_size / longer_side
    
    if total_pixels > max_pixels:
        scale_total_res = math.sqrt(max_pixels / total_pixels)
    
    # Use the more restrictive scale factor (smaller value)
    scale = min(scale_longer_side, scale_total_res)
    
    if scale < 1.0:
        new_width = int(width * scale)
        new_height = int(height * scale)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        print(f"  Resized from {width}x{height} ({total_pixels/1_000_000:.2f}MP) to {new_width}x{new_height} ({new_width*new_height/1_000_000:.2f}MP)")
    
    return img


def _try_import_deps_manager():
    """Best-effort import of deps_manager from the same directory as this script."""
    try:
        import importlib.util, sys as _sys
        script_dir = Path(__file__).parent
        spec = importlib.util.spec_from_file_location("deps_manager", script_dir / "deps_manager.py")
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    except Exception:
        pass
    try:
        import deps_manager
        return deps_manager
    except Exception:
        pass
    return None


def find_poppler_path():
    """
    Try to find Poppler installation.
    Checks PATH, known paths, and our managed AppData install.
    If not found, offers to auto-install (downloading ~30 MB from GitHub).
    Falls back to manual folder selection only if user declines auto-install.
    """
    # 1. Already in PATH
    if shutil.which("pdftoppm"):
        return None

    # 2. Check all known locations (including our managed AppData install)
    localappdata = os.environ.get("LOCALAPPDATA", "")
    managed_bin_candidates = [
        os.path.join(localappdata, "StillMotion", "poppler", "Library", "bin"),
        os.path.join(localappdata, "StillMotion", "poppler", "bin"),
    ]
    common_paths = managed_bin_candidates + [
        r"C:\modues\poppler\Release-24.08.0-0\poppler-24.08.0\Library\bin",
        r"C:\modues\poppler\Library\bin",
        r"C:\poppler\Release-24.08.0-0\poppler-24.08.0\Library\bin",
        r"C:\poppler\Library\bin",
        r"C:\poppler\bin",
        r"C:\Program Files\poppler\bin",
        r"C:\Program Files (x86)\poppler\bin",
        os.path.expanduser(r"~\poppler\Library\bin"),
        os.path.expanduser(r"~\poppler\bin"),
    ]
    for path in common_paths:
        try:
            p = Path(path)
            if not p.exists():
                continue
            exe = p / "pdftoppm.exe"
            if not exe.exists():
                continue
            # Verify the binary is actually executable by the current user
            subprocess.run([str(exe), "-v"], capture_output=True, timeout=5)
            return str(p)
        except (PermissionError, OSError):
            continue  # installed by another account — skip

    # 3. Not found — offer automatic install
    root = tk.Tk()
    root.withdraw()

    answer = messagebox.askyesno(
        "Poppler Required",
        "PDF Magician needs Poppler (a free tool) to convert PDFs.\n\n"
        "It is not installed on this PC.\n\n"
        "Download and install automatically? (~30 MB)\n\n"
        "(No admin rights required — installs to your user folder)"
    )

    if answer:
        # Run auto-install using deps_manager
        dm = _try_import_deps_manager()
        if dm and hasattr(dm, "install_poppler_silent"):
            log_lines = []
            def log_cb(msg):
                log_lines.append(msg)
                print(msg)

            # Show a simple progress window
            prog_win = tk.Toplevel()
            prog_win.title("Installing Poppler...")
            prog_win.resizable(False, False)
            prog_win.attributes("-topmost", True)
            tk.Label(prog_win, text="Downloading and installing Poppler.\nPlease wait...", padx=20, pady=20).pack()
            prog_win.update()

            bin_path = dm.install_poppler_silent(log_cb)

            prog_win.destroy()

            if bin_path:
                messagebox.showinfo(
                    "Poppler Installed",
                    f"Poppler installed successfully!\n\nLocation: {bin_path}\n\n"
                    "PDF conversion is now ready."
                )
                return bin_path
            else:
                messagebox.showerror(
                    "Install Failed",
                    "Automatic installation failed.\n\n"
                    "Please install manually:\n"
                    "https://github.com/oschwartz10612/poppler-windows/releases/"
                )
                return None
        else:
            messagebox.showerror(
                "Install Unavailable",
                "Auto-install module not found.\n\n"
                "Please install manually:\n"
                "https://github.com/oschwartz10612/poppler-windows/releases/"
            )
            return None
    else:
        # User declined auto-install — let them pick the folder manually
        messagebox.showinfo(
            "Manual Selection",
            "Please select the Poppler 'bin' folder (the one containing pdftoppm.exe)."
        )
        poppler_bin = filedialog.askdirectory(
            title="Select Poppler 'bin' folder (should contain pdftoppm.exe)"
        )
        if poppler_bin and Path(poppler_bin).joinpath("pdftoppm.exe").exists():
            return poppler_bin
        return None


def calculate_safe_dpi(pdf_path: Path, poppler_path: str = None, target_dpi: int = 300) -> int:
    """Calculate a DPI that keeps the resulting image within PIL's pixel limit.
    
    Returns the target_dpi if safe, or a reduced DPI if the image would be too large.
    """
    try:
        # Get PDF info to determine page dimensions
        if poppler_path:
            info = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)
        else:
            info = pdfinfo_from_path(pdf_path)
        
        # PDF dimensions are in points (1 inch = 72 points)
        # At target_dpi, the pixel dimensions would be: (width_pts / 72) * dpi
        page_size = info.get('Page size', '')
        
        # Parse page size string like "1190.55 x 841.89 pts"
        if 'x' in page_size:
            parts = page_size.lower().replace('pts', '').strip().split('x')
            if len(parts) == 2:
                try:
                    width_pts = float(parts[0].strip())
                    height_pts = float(parts[1].strip())
                    
                    # Calculate pixel dimensions at target DPI
                    width_px = (width_pts / 72.0) * target_dpi
                    height_px = (height_pts / 72.0) * target_dpi
                    total_pixels = width_px * height_px
                    
                    # If within limit, use target DPI
                    if total_pixels <= PIL_MAX_PIXELS:
                        return target_dpi
                    
                    # Calculate the scale factor needed to fit within limit
                    scale = math.sqrt(PIL_MAX_PIXELS / total_pixels)
                    safe_dpi = int(target_dpi * scale * 0.95)  # 5% safety margin
                    
                    print(f"  PDF page size: {width_pts:.0f}x{height_pts:.0f} pts")
                    print(f"  At {target_dpi} DPI would be {width_px:.0f}x{height_px:.0f} ({total_pixels/1_000_000:.1f}MP)")
                    print(f"  Reducing DPI to {safe_dpi} to stay within {PIL_MAX_PIXELS/1_000_000:.0f}MP limit")
                    
                    return max(safe_dpi, 72)  # Minimum 72 DPI
                except ValueError:
                    pass
        
        # If we can't parse the page size, return target DPI and let it fail if too large
        return target_dpi
        
    except Exception as e:
        print(f"  Warning: Could not get PDF info: {e}")
        return target_dpi


def convert_pdf_to_jpgs(pdf_path: Path, poppler_path: str = None, dpi: int = 300, fmt: str = "jpeg") -> None:
    """Convert a single PDF to JPGs saved alongside the PDF.
    
    Automatically reduces DPI for large PDFs to stay within PIL's pixel limit.
    """
    try:
        # Calculate safe DPI that won't exceed PIL's limit
        safe_dpi = calculate_safe_dpi(pdf_path, poppler_path, dpi)
        
        if poppler_path:
            pages = convert_from_path(pdf_path, dpi=safe_dpi, fmt=fmt, poppler_path=poppler_path)
        else:
            pages = convert_from_path(pdf_path, dpi=safe_dpi, fmt=fmt)
        
        base = pdf_path.stem
        for idx, img in enumerate(pages, start=1):
            # Resize if longer side exceeds 8000px or total resolution exceeds 24MP
            img = resize_if_needed(img, max_size=8000, max_mp=24)
            
            out_path = pdf_path.parent / f"{base}_page-{idx}.{fmt}"
            img.save(out_path, fmt.upper(), quality=95)
            print(f"Saved {out_path}")
    except Exception as e:
        print(f"Error converting {pdf_path.name}: {e}")
        raise


def run_pdf_to_jpg():
    """Run the PDF to JPG conversion function."""
    try:
        _run_pdf_to_jpg_inner()
    except Exception as e:
        import traceback
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("PDF to JPG Error", f"{e}\n\n{traceback.format_exc()}")


def _run_pdf_to_jpg_inner():
    # Find poppler path
    poppler_path = find_poppler_path()

    if poppler_path is None and not shutil.which("pdftoppm"):
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        messagebox.showerror(
            "Poppler Required",
            "Poppler is required but not found.\n\n"
            "Please install poppler and try again.\n\n"
            "Download from: https://github.com/oschwartz10612/poppler-windows/releases/"
        )
        return

    # Create a helper root window that stays on top so the file picker
    # appears in front of other windows (important when launched as subprocess)
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.lift()
    root.focus_force()

    selected_files = filedialog.askopenfilenames(
        title="Select PDF files to convert",
        filetypes=[("PDF files", "*.pdf")],
        parent=root,
    )

    if not selected_files:
        print("No files selected. Exiting.")
    else:
        print(f"Converting {len(selected_files)} PDF file(s)...")
        for pdf in selected_files:
            try:
                convert_pdf_to_jpgs(Path(pdf), poppler_path=poppler_path, dpi=300, fmt="jpeg")
                print(f"[OK] Completed: {Path(pdf).name}")
            except Exception as e:
                print(f"[ERROR] Failed: {Path(pdf).name} - {e}")
        
        messagebox.showinfo("Conversion Complete", f"Processed {len(selected_files)} file(s).")


def find_scanner(scanner_name: str = "BRW94533072ACFD", scanner_ip: str = "192.168.50.239"):
    """Find the specified scanner using WIA."""
    try:
        manager = win32com.client.Dispatch("WIA.DeviceManager")
        
        # Try to find the scanner
        devices = manager.DeviceInfos
        found_device = None
        
        print(f"  Searching for scanner among {devices.Count} device(s)...")
        
        for i in range(1, devices.Count + 1):
            device_info = devices.Item(i)
            try:
                device_id = device_info.DeviceID
                device_name = device_info.Properties("Name").Value
                
                print(f"    Device {i}: {device_name} (ID: {device_id})")
                
                # Check if this is our scanner by various criteria
                device_id_lower = device_id.lower()
                device_name_lower = device_name.lower()
                
                # Check by scanner name/ID
                if scanner_name.lower() in device_id_lower:
                    print(f"  Found scanner by ID: {device_name}")
                    found_device = device_info
                    break
                
                # Check by device name containing "Brother" or "ADS"
                if 'brother' in device_name_lower or 'ads-1600' in device_name_lower:
                    print(f"  Found Brother scanner: {device_name}")
                    found_device = device_info
                    break
                
                # Check by IP if available
                try:
                    for prop in device_info.Properties:
                        prop_value = str(prop.Value).lower()
                        if scanner_ip in prop_value:
                            print(f"  Found scanner by IP: {device_name}")
                            found_device = device_info
                            break
                except:
                    pass
                    
                if found_device:
                    break
                    
            except Exception as e:
                print(f"    Error checking device {i}: {e}")
                continue
        
        if found_device:
            return found_device.Connect()
        
        # If not found automatically, show device selection dialog
        print("  Scanner not found automatically. Showing device selection...")
        wia = win32com.client.Dispatch("WIA.CommonDialog")
        device = wia.ShowSelectDevice()
        return device
        
    except Exception as e:
        print(f"Error finding scanner: {e}")
        raise


def get_property_value_safe(item, prop_id, default=None):
    """Safely get a property value from a WIA item."""
    try:
        return item.Properties(str(prop_id)).Value
    except:
        return default


def set_property_value_safe(item, prop_id, value, name="property"):
    """Safely set a property value on a WIA item. Returns True if successful."""
    try:
        item.Properties(str(prop_id)).Value = value
        actual = item.Properties(str(prop_id)).Value
        print(f"    Set {name} to {value} (actual: {actual})")
        return True
    except Exception as e:
        print(f"    Could not set {name}: {e}")
        return False


def scan_all_pages(device, output_folder: Path):
    """Scan all pages from the scanner and save as PDF. Auto-configured for A4, full color, duplex."""
    try:
        images = []
        
        print("Configuring scanner for duplex color scanning...")

        # --- Check scanner capabilities ---
        caps = 0
        duplex_supported = False
        try:
            caps = device.Properties("3086").Value
            duplex_supported = (caps & 4) != 0
            print(f"  Scanner capabilities: FEEDER={'Yes' if caps&1 else 'No'}, DUPLEX={'Yes' if duplex_supported else 'No'}")
        except Exception as e:
            print(f"  Could not read capabilities: {e}")

        # --- Enable DUPLEX mode if supported ---
        if duplex_supported:
            try:
                # Set document handling to FEEDER (1) + DUPLEX (4) = 5
                device.Properties("3088").Value = 5
                print("  Enabled DUPLEX mode (scanning both sides)")
            except Exception as e:
                print(f"  Could not enable duplex: {e}")

        # --- Get the scan item ---
        try:
            item = device.Items(1)
        except Exception as e:
            print(f"  Error: Could not get scanner item: {e}")
            messagebox.showerror("Scanner Error", "Could not get a valid scanner item.")
            return

        # --- Scan all pages ---
        print("\nScanning...")
        page_count = 0
        
        while True:
            try:
                image = item.Transfer()
                if image is None:
                    break
                    
                image_file = image.FileData
                image_stream = io.BytesIO(image_file.BinaryData)
                pil_image = Image.open(image_stream).copy()
                images.append(pil_image)
                page_count += 1
                print(f"  Page {page_count} scanned ({pil_image.size[0]}x{pil_image.size[1]})")
                
            except Exception as e:
                error_str = str(e).lower()
                # Check for "paper empty" / "no more pages" - this is normal end of scan
                if ('paper' in error_str or 'empty' in error_str or 
                    'no document' in error_str or '-2145320957' in str(e) or
                    '-2145320939' in str(e)):
                    break
                else:
                    # Real error - stop scanning
                    print(f"  Scan error: {e}")
                    break
        
        print(f"\nScan complete: {len(images)} pages captured.")

        if not images:
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("No Pages", "No pages were scanned.\n\nPlease check:\n1. Paper is loaded in the ADF\n2. Scanner is ready")
            return

        # --- Re-enabled Blank Page Detection ---
        print("\nDetecting and removing blank pages...")
        final_images = []
        for idx, img in enumerate(images, 1):
            if not is_blank(img):
                final_images.append(img)
                print(f"  Keeping page {idx} (not blank).")
            else:
                print(f"  Discarding page {idx} (blank).")

        print(f"\nAfter blank page removal: {len(final_images)} pages remaining.")

        if not final_images:
            print("All pages were blank.")
            messagebox.showwarning("No Pages", "All pages were blank and have been discarded.")
            return
        
        # Create PDF from images
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = output_folder / f"scan_{timestamp}.pdf"
        
        print(f"\nCreating PDF: {pdf_path}")
        create_pdf_from_images(final_images, pdf_path)
        print(f"[OK] PDF created: {pdf_path}")
        
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "Scan Complete",
            f"Scanned {len(final_images)} page(s) (after removing blank pages)\n\n"
            f"Saved to: {pdf_path}"
        )
        
    except Exception as e:
        print(f"Error during scanning: {e}")
        import traceback
        traceback.print_exc()
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Scan Error", f"Error during scanning:\n{e}")
        raise


def create_pdf_from_images(images: list, output_path: Path):
    """Create a PDF file from a list of PIL Images with proper A4 page size.
    Automatically rotates landscape images to portrait and scales to fit A4."""
    if not images:
        return
    
    # A4 dimensions in pixels at 300 DPI: 2480 x 3508 (210mm x 297mm)
    A4_WIDTH = 2480
    A4_HEIGHT = 3508
    A4_DPI = 300
    
    # Convert all images to RGB if needed (PDF requires RGB)
    # Rotate landscape images to portrait, then resize to fit A4
    rgb_images = []
    for idx, img in enumerate(images, 1):
        if img.mode != 'RGB':
            rgb_img = img.convert('RGB')
        else:
            rgb_img = img.copy()
        
        width, height = rgb_img.size
        print(f"    Processing page {idx}: original size {width}x{height}")
        
        # If image is landscape (wider than tall), rotate it to portrait
        # This fixes the scanner outputting landscape images for A4 documents
        if width > height:
            print(f"      Rotating landscape to portrait...")
            rgb_img = rgb_img.rotate(90, expand=True)
            width, height = rgb_img.size
            print(f"      After rotation: {width}x{height}")
        
        # Now scale to fit A4 while preserving aspect ratio
        scale_w = A4_WIDTH / width
        scale_h = A4_HEIGHT / height
        scale = min(scale_w, scale_h)  # Use smaller scale to fit both dimensions
        
        # Resize to fit A4
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        # Resize the image
        rgb_img = rgb_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Create A4-sized canvas and paste the image centered
        a4_canvas = Image.new('RGB', (A4_WIDTH, A4_HEIGHT), color='white')
        
        # Calculate position to center the image
        x_offset = (A4_WIDTH - new_width) // 2
        y_offset = (A4_HEIGHT - new_height) // 2
        
        # Paste the resized image onto the A4 canvas
        a4_canvas.paste(rgb_img, (x_offset, y_offset))
        
        print(f"      Final: {new_width}x{new_height} centered on A4 ({A4_WIDTH}x{A4_HEIGHT})")
        
        rgb_images.append(a4_canvas)
    
    # Save as PDF
    if len(rgb_images) == 1:
        rgb_images[0].save(output_path, 'PDF', resolution=A4_DPI)
    else:
        rgb_images[0].save(
            output_path,
            'PDF',
            resolution=A4_DPI,
            save_all=True,
            append_images=rgb_images[1:]
        )


def run_scanner():
    """Run the scanner function."""
    scanner_name = "BRW94533072ACFD"
    scanner_ip = "192.168.50.239"
    output_folder = Path(r"C:\Users\wikto\iCloudDrive\scans 2D")
    
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"Connecting to scanner: {scanner_name} ({scanner_ip})")
        device = find_scanner(scanner_name, scanner_ip)
        
        if device is None:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Scanner Not Found",
                f"Could not find scanner: {scanner_name}\n\n"
                "Please ensure:\n"
                "1. Scanner is powered on\n"
                "2. Scanner is connected to the network\n"
                "3. Scanner drivers are installed"
            )
            return
        
        print(f"Scanner connected: {device.Properties('Name').Value}")
        scan_all_pages(device, output_folder)
        
    except Exception as e:
        print(f"Error: {e}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Scanner Error", f"Error accessing scanner:\n{e}")


if __name__ == "__main__":
    function = show_function_menu()
    
    if function == "pdf_to_jpg":
        run_pdf_to_jpg()
    elif function == "scan":
        run_scanner()
    else:
        print("Exiting.")
