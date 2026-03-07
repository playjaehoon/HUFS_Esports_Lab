import sys
import os

try:
    from PIL import Image
    # Adobe Illustrator files sometimes just open as PDF streams in Pillow
    img = Image.open('C:/EsportsLab/static/images/logo.ai')
    img.save('C:/EsportsLab/static/images/logo.png', 'PNG')
    print("Success natively with Pillow")
    sys.exit(0)
except Exception as e:
    print(f"Pillow failed: {e}")

try:
    # Try fetching as Ghostscript
    import ghostscript
    args = [
        "gs", 
        "-dNOPAUSE", 
        "-dBATCH", 
        "-sDEVICE=pngalpha", 
        "-r300", 
        "-sOutputFile=C:/EsportsLab/static/images/logo.png", 
        "C:/EsportsLab/static/images/logo.ai"
    ]
    ghostscript.Ghostscript(*args)
    print("Success with ghostscript")
except Exception as e:
    print(f"Ghostscript failed: {e}")
