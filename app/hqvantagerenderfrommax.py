import sys
import os
import time

# -----------------------------------------------------------------------------
# SETUP & IMPORTS
# -----------------------------------------------------------------------------
try:
    import pymxs
except ImportError:
    print("\n[ERROR] 'pymxs' module not found.")
    print("This script must be run INSIDE 3ds Max (Scripting > Run Script...).")
    print("It cannot be run from a standard external Python terminal.\n")
    sys.exit(1)

# Try to import vray (AppSDK). If missing, try to add common paths.
try:
    import vray
except ImportError:
    # Common paths for V-Ray AppSDK (adjust if installed elsewhere)
    possible_paths = [
        r"C:\Program Files\Chaos Group\V-Ray\AppSDK\python3",
        r"C:\Program Files\Chaos Group\V-Ray\3ds Max 2024\AppSDK\python3", # Example year
        r"C:\Program Files\Chaos Group\V-Ray\3ds Max 2023\AppSDK\python3",
        r"C:\Program Files\Chaos Group\V-Ray\3ds Max 2022\AppSDK\python3",
        r"C:\Program Files\Chaos Group\V-Ray\3ds Max 2025\AppSDK\python3",
    ]
    
    found = False
    for p in possible_paths:
        if os.path.exists(p):
            if p not in sys.path:
                sys.path.append(p)
            try:
                import vray
                print(f"Loaded vray module from: {p}")
                found = True
                break
            except ImportError:
                continue
    
    if not found:
        print("\n[WARNING] 'vray' module (V-Ray AppSDK) not found.")
        print("Please ensure V-Ray AppSDK is installed and its 'python3' folder is in sys.path.")
        print("You may need to edit this script to add your specific AppSDK path.\n")
        # We don't exit here, as the export part might still work, but render will fail.

def render_current_view_to_vantage():
    # 1. SETUP PATHS
    # Get the current 3ds Max project folder
    try:
        proj_path = pymxs.runtime.getDir(pymxs.runtime.Name("project"))
    except Exception:
        # Fallback if getDir fails or returns empty
        proj_path = os.path.expanduser("~")

    output_folder = os.path.join(proj_path, "vantage_renders")
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Temporary file for the current frame (will be overwritten/deleted)
    temp_vrscene = os.path.join(output_folder, "temp_frame_snapshot.vrscene")
    
    # Path to your lightweight config (CHANGE THIS TO YOUR ACTUAL CONFIG PATH)
    config_path = "C:/path/to/your/template.vantage" 
    
    # Generate filename based on current time/frame
    curr_frame = int(pymxs.runtime.sliderTime)
    output_filename = os.path.join(output_folder, f"Render_Frame_{curr_frame:04d}.png")

    print(f"--- Starting Vantage Render for Frame {curr_frame} ---")

    # 2. EXPORT CURRENT FRAME FROM 3DS MAX
    # This uses the built-in V-Ray command to dump the current state to a vrscene
    # We use frame and frame+1 to ensure only a single-frame snapshot is taken
    
    # NOTE: 'vrayExportRTScene' is likely incorrect. Replaced with 'vrayExportVRScene'.
    # If vrayExportVRScene is not available, we might need to use renderer properties.
    try:
        # pymxs.runtime.vrayExportVRScene(filename, start, end)
        # Note: In MaxScript, arguments are positional. In pymxs, we pass them as args.
        pymxs.runtime.vrayExportVRScene(temp_vrscene, curr_frame, curr_frame)
    except AttributeError:
        print("[ERROR] 'vrayExportVRScene' function not found in pymxs.runtime.")
        print("Please ensure V-Ray is installed and loaded in 3ds Max.")
        return
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")
        return

    # 3. USE VANTAGE SDK TO RENDER
    if 'vray' not in sys.modules:
        print("Skipping render because 'vray' module was not loaded.")
        return

    try:
        with vray.VRayRenderer() as renderer:
            # Tell the SDK to use the Vantage Engine (lav)
            renderer.config.type = 'lav' 
            
            # Load the 3D data from the temp file
            renderer.load(temp_vrscene)
            
            # LOAD CONFIG: This applies your lights/LUTs/quality settings
            if os.path.exists(config_path):
                renderer.load(config_path)
            else:
                print("Warning: Config file not found. Rendering with default Vantage settings.")

            # Trigger the High-Quality render
            print("Vantage is processing...")
            renderer.start_sync()
            renderer.wait_for_render_end()
            
            # Save the result
            renderer.save_image(output_filename)
            print(f"Success! Render saved to: {output_filename}")

    except Exception as e:
        print(f"Error during Vantage Render: {e}")

    # 4. CLEANUP
    if os.path.exists(temp_vrscene):
        try:
            os.remove(temp_vrscene)
        except OSError:
            pass