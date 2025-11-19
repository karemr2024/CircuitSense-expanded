import fitz
import logging
import os
import subprocess
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

def preprocess_latex(latex_code):
    latex_code = latex_code.strip()
    latex_code = latex_code.replace(r"\documentclass{article}", r"\documentclass[border=10pt]{standalone}")
    latex_code = latex_code.replace(r"\begin{center}", r"")
    latex_code = latex_code.replace(r"\end{center}", r"")
    latex_code = latex_code.replace(")\n\\draw", ");\n\\draw")
    return latex_code

def pdf2jpg(pdfPath, imgPath, zoom_x, zoom_y, rotation_angle=0, reconvert=False):
    """Convert PDF to JPG image.
    
    Args:
        pdfPath: Path to input PDF file
        imgPath: Path to output JPG file
        zoom_x: Horizontal zoom factor
        zoom_y: Vertical zoom factor
        rotation_angle: Rotation angle in degrees
        reconvert: If True, reconvert even if output exists
    
    Returns:
        True if successful, False otherwise
    """
    try:
        pdf = fitz.open(pdfPath)
        if os.path.exists(imgPath) and not reconvert:
            logger.debug(f"Image file {imgPath} already exists, skipping conversion")
            return True
        assert pdf.page_count > 0, "PDF page count is 0"
        
        page = pdf[0]
        trans = fitz.Matrix(zoom_x, zoom_y).prerotate(rotation_angle)
        pm = page.get_pixmap(matrix=trans, alpha=False)
        pm._writeIMG(imgPath, format_="jpg", jpg_quality=100)
        pdf.close()
        image = Image.open(imgPath)

        width, height = image.size
        logger.debug(f"PDF converted to JPG: {imgPath} ({width}x{height})")
        return True
    except Exception as e:
        logger.error(f"Failed to convert PDF {pdfPath} to JPG: {e}")
        return False

def compile_latex(folder, file_name, latex_code):
    """Compile LaTeX code to PDF.
    
    Args:
        folder: Directory to save output files
        file_name: Base name for LaTeX file (without .tex extension)
        latex_code: LaTeX source code
    
    Returns:
        True if successful, False otherwise
    """
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    
    tex_file = folder_path / f"{file_name}.tex"
    pdf_file = folder_path / f"{file_name}.pdf"
    
    with open(tex_file, "w", encoding='utf-8') as f:
        f.write(latex_code)
    
    # Try pdflatex first
    try:
        result = subprocess.run(
            ["pdflatex", "-interaction=batchmode", f"-output-directory={folder}", str(tex_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 and pdf_file.exists():
            logger.debug(f"Successfully compiled LaTeX with pdflatex: {tex_file}")
            return True
    except subprocess.TimeoutExpired:
        logger.warning(f"pdflatex timed out for {tex_file}")
    except Exception as e:
        logger.debug(f"pdflatex failed for {tex_file}: {e}")
    
    # Try xelatex as fallback
    try:
        result = subprocess.run(
            ["xelatex", "-interaction=batchmode", f"-output-directory={folder}", str(tex_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 and pdf_file.exists():
            logger.debug(f"Successfully compiled LaTeX with xelatex: {tex_file}")
            return True
        else:
            logger.warning(f"xelatex failed for {tex_file} (return code: {result.returncode})")
            if result.stderr:
                logger.debug(f"xelatex stderr: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        logger.warning(f"xelatex timed out for {tex_file}")
    except Exception as e:
        logger.error(f"xelatex error for {tex_file}: {e}")
    
    logger.error(f"Failed to compile LaTeX: {tex_file}")
    return False

if __name__ == "__main__":
    path = "test.pdf"
    save_path = path.replace(".pdf", ".jpg")
    pdf2jpg(pdfPath=path, imgPath=save_path, zoom_x=1, zoom_y=1, rotation_angle=0)
