import io
import base64
import numpy as np
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter


def load_image(file_bytes: bytes, filename: str):
    """Load image from bytes, supporting DICOM and standard formats.
    Returns (PIL.Image, dicom_dataset_or_None).
    """
    suffix = Path(filename).suffix.lower()
    if suffix in ('.dcm', '.dicom'):
        return _load_dicom(file_bytes)
    return _load_standard(file_bytes), None


def _load_dicom(file_bytes: bytes):
    try:
        import pydicom
        from pydicom.filebase import DicomBytesIO
    except ImportError:
        raise ImportError("pydicom is required for DICOM files. Run: pip install pydicom")

    ds = pydicom.dcmread(DicomBytesIO(file_bytes))
    arr = ds.pixel_array.astype(float)
    arr = ((arr - arr.min()) / (arr.max() - arr.min() + 1e-9) * 255).astype(np.uint8)

    if arr.ndim == 2:
        img = Image.fromarray(arr, mode='L').convert('RGB')
    else:
        img = Image.fromarray(arr)

    return img, ds


def _load_standard(file_bytes: bytes):
    return Image.open(io.BytesIO(file_bytes)).convert('RGB')


def enhance_image(img: Image.Image, mode: str = 'original') -> Image.Image:
    """Apply image enhancement suited to dental X-ray review."""
    if mode == 'original':
        return img

    gray = img.convert('L')
    arr = np.array(gray)

    if mode == 'clahe':
        try:
            import cv2
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(arr)
            return Image.fromarray(enhanced).convert('RGB')
        except ImportError:
            # Fallback: manual histogram equalization via Pillow
            from PIL import ImageOps
            return ImageOps.equalize(gray).convert('RGB')

    elif mode == 'contrast':
        return ImageEnhance.Contrast(img).enhance(2.2)

    elif mode == 'brightness':
        return ImageEnhance.Brightness(img).enhance(1.4)

    elif mode == 'sharpen':
        return ImageEnhance.Sharpness(img).enhance(3.0)

    elif mode == 'inverted':
        return Image.fromarray(255 - arr).convert('RGB')

    elif mode == 'edges':
        return img.filter(ImageFilter.FIND_EDGES).convert('RGB')

    elif mode == 'emboss':
        return img.filter(ImageFilter.EMBOSS).convert('RGB')

    return img


def image_to_base64(img: Image.Image) -> str:
    """Encode a PIL image as a JPEG base64 string for the Claude API."""
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def get_image_bytes(img: Image.Image, fmt: str = 'JPEG') -> bytes:
    """Return raw bytes for a PIL image (used for downloads and PDF embedding)."""
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=95)
    return buf.getvalue()
