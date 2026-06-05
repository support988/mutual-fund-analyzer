import os
import sys

def get_base_path():
    """ Get absolute path to base directory, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    return os.path.join(get_base_path(), relative_path)

def get_app_data_path(filename):
    """ Get path to writable application data, like config.json. 
    If the file doesn't exist in the writable location, it copies a default 
    version from the bundled resources if available.
    """
    if getattr(sys, 'frozen', False):
        # When running as exe, store config next to the exe
        base_path = os.path.dirname(sys.executable)
    else:
        # In dev, store in the project root
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    target_path = os.path.join(base_path, filename)
    
    # If it doesn't exist in the target location, try to copy from bundled resources
    if not os.path.exists(target_path):
        try:
            resource_path = get_resource_path(filename)
            if os.path.exists(resource_path) and resource_path != target_path:
                import shutil
                shutil.copy2(resource_path, target_path)
        except Exception as e:
            print(f"Error copying default {filename}: {e}")
                
    return target_path
