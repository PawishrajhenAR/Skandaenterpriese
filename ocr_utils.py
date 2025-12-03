import os
import logging

# Fix PIL compatibility issue with newer Pillow versions
try:
    from PIL import Image
    # Pillow 10+ removed ANTIALIAS, use LANCZOS instead
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
except ImportError:
    pass

# Cache for EasyOCR reader to avoid re-initialization
_ocr_reader = None

logger = logging.getLogger(__name__)


def get_ocr_reader():
    """
    Get or create the EasyOCR reader instance.
    Caches the reader to avoid re-initialization on every OCR call.
    """
    global _ocr_reader
    
    if _ocr_reader is None:
        try:
            import easyocr
            logger.info("Initializing EasyOCR reader (this may take 10-30 seconds on first run)...")
            # Initialize with English language only for better performance
            _ocr_reader = easyocr.Reader(['en'], gpu=False)
            logger.info("EasyOCR reader initialized successfully")
        except ImportError:
            logger.error("EasyOCR not installed")
            raise ImportError("OCR engine not installed. Please install easyocr: pip install easyocr")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {str(e)}")
            raise Exception(f"Failed to initialize OCR engine: {str(e)}")
    
    return _ocr_reader


def run_ocr(image_path):
    """
    Run OCR on an image file.
    Returns extracted text or a message if OCR engine is not available.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        str: Extracted text from the image
    """
    try:
        # Check if file exists
        if not os.path.exists(image_path):
            return f"Error: Image file not found at {image_path}"
        
        # Get cached reader
        reader = get_ocr_reader()
        
        # Run OCR
        logger.info(f"Processing OCR for image: {image_path}")
        result = reader.readtext(image_path)
        
        # Extract text from EasyOCR results
        # EasyOCR returns: [(bbox, text, confidence), ...]
        text_parts = []
        for item in result:
            if len(item) >= 2:
                text = item[1]  # Extract text (second element)
                confidence = item[2] if len(item) > 2 else 1.0  # Confidence score
                # Only include text with reasonable confidence (> 0.3)
                if confidence > 0.3:
                    text_parts.append(text)
        
        # Join text parts with newlines for better readability
        extracted_text = '\n'.join(text_parts)
        
        if not extracted_text.strip():
            return "No text could be extracted from the image. Please ensure the image is clear and contains readable text."
        
        logger.info(f"OCR completed. Extracted {len(text_parts)} text blocks")
        return extracted_text
        
    except ImportError:
        return "OCR engine not installed. Please install easyocr: pip install easyocr"
    except Exception as e:
        error_msg = f"OCR error: {str(e)}"
        logger.error(error_msg)
        return error_msg
