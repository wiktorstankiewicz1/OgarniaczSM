#!/usr/bin/env python3
"""
Helper script to download and set up Poppler for Windows.
"""

import os
import zipfile
import urllib.request
import shutil
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

POPPLER_URL = "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.07.0-0/Release-24.07.0-0.zip"
# Install location requested by user
INSTALL_DIR = Path("C:/modues/poppler")


def download_poppler():
    """Download and extract poppler to C:/modues/poppler (or fallback to user folder)"""
    print("Downloading Poppler...")
    print(f"URL: {POPPLER_URL}")
    
    # Use temp directory instead of C:\ root
    temp_dir = Path(tempfile.gettempdir())
    zip_path = temp_dir / "poppler_temp.zip"
    
    try:
        # Download
        print("Downloading (this may take a few minutes)...")
        urllib.request.urlretrieve(POPPLER_URL, zip_path)
        print("Download complete!")
        
        # Extract to temp first, then move to final location
        print(f"Extracting...")
        extract_temp = temp_dir / "poppler_extract"
        if extract_temp.exists():
            shutil.rmtree(extract_temp)
        extract_temp.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_temp)
        
        # Find the actual poppler folder in the extracted files
        extracted_dirs = list(extract_temp.glob("poppler-*"))
        if not extracted_dirs:
            # Try looking for Library/bin directly
            extracted_dirs = list(extract_temp.glob("*"))
        
        if extracted_dirs:
            source_dir = extracted_dirs[0]
            # Use a local variable for the final install directory
            install_dir = INSTALL_DIR
            # Try to create install directory
            try:
                if install_dir.exists():
                    shutil.rmtree(install_dir)
                install_dir.mkdir(parents=True, exist_ok=True)
                # Move contents
                for item in source_dir.iterdir():
                    shutil.move(str(item), str(install_dir / item.name))
            except PermissionError:
                # Try user directory instead
                install_dir = Path.home() / "poppler"
                if install_dir.exists():
                    shutil.rmtree(install_dir)
                install_dir.mkdir(parents=True, exist_ok=True)
                for item in source_dir.iterdir():
                    shutil.move(str(item), str(install_dir / item.name))
                print(f"Note: Installed to {install_dir} (C:\\ root requires admin)")
        
        # Clean up temp extraction folder
        if extract_temp.exists():
            shutil.rmtree(extract_temp)
        
        # Clean up
        zip_path.unlink()
        
        # Find bin folder
        bin_paths = [
            install_dir / "Library" / "bin",
            install_dir / "bin",
        ]
        
        for bin_path in bin_paths:
            if bin_path.exists() and (bin_path / "pdftoppm.exe").exists():
                print(f"\n[OK] Poppler installed successfully!")
                print(f"  Location: {bin_path}")
                return str(bin_path)
        
        print(f"\n[OK] Poppler extracted to: {install_dir}")
        print("  Please locate the 'bin' folder manually.")
        return str(install_dir)
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("\nManual installation:")
        print("1. Go to: https://github.com/oschwartz10612/poppler-windows/releases/")
        print("2. Download the latest Release-*.zip file")
        print(f"3. Extract it to C:\\modues\\poppler")
        print("4. Find the 'Library\\bin' folder inside")
        return None


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    
    response = messagebox.askyesno(
        "Install Poppler",
        "This will download and install Poppler to C:\\modues\\poppler\n\n"
        "Do you want to continue?\n\n"
        "(You can also install manually from:\n"
        "https://github.com/oschwartz10612/poppler-windows/releases/)"
    )
    
    if response:
        bin_path = download_poppler()
        if bin_path:
            messagebox.showinfo(
                "Success",
                f"Poppler installed!\n\n"
                f"Bin folder: {bin_path}\n\n"
                f"You can now run pdftojpg.py"
            )
        else:
            messagebox.showerror(
                "Installation Failed",
                "Automatic installation failed.\n\n"
                "Please install manually:\n"
                "1. Go to: https://github.com/oschwartz10612/poppler-windows/releases/\n"
                "2. Download the latest Release-*.zip\n"
                "3. Extract to C:\\modues\\poppler\n"
                "4. Run pdftojpg.py and select the 'Library\\bin' folder when prompted"
            )
    else:
        print("Installation cancelled.")

