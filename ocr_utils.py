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
_gpu_available = None

logger = logging.getLogger(__name__)


def check_gpu_availability():
    """Check if GPU is available for OCR processing"""
    global _gpu_available
    
    if _gpu_available is not None:
        return _gpu_available
    
    try:
        import torch
        _gpu_available = torch.cuda.is_available()
        if _gpu_available:
            logger.info(f"GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            logger.info("GPU not available, using CPU")
    except ImportError:
        logger.info("PyTorch not available, using CPU")
        _gpu_available = False
    except Exception as e:
        logger.warning(f"Error checking GPU availability: {e}, using CPU")
        _gpu_available = False
    
    return _gpu_available


def get_ocr_reader():
    """
    Get or create the EasyOCR reader instance with GPU support.
    Caches the reader to avoid re-initialization on every OCR call.
    Automatically detects and uses GPU if available, falls back to CPU.
    """
    global _ocr_reader
    
    if _ocr_reader is None:
        try:
            import easyocr
            use_gpu = check_gpu_availability()
            
            logger.info(f"Initializing EasyOCR reader (GPU: {'enabled' if use_gpu else 'disabled'})...")
            logger.info("This may take 10-30 seconds on first run...")
            
            # Initialize with English language and GPU support
            # Use GPU if available, otherwise fall back to CPU
            _ocr_reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
            
            logger.info(f"EasyOCR reader initialized successfully (GPU: {'enabled' if use_gpu else 'disabled'})")
        except ImportError:
            logger.error("EasyOCR not installed")
            raise ImportError("OCR engine not installed. Please install easyocr: pip install easyocr")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {str(e)}")
            # Try CPU fallback if GPU initialization failed
            if 'gpu' in str(e).lower() or 'cuda' in str(e).lower():
                logger.info("GPU initialization failed, trying CPU fallback...")
                try:
                    _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
                    logger.info("EasyOCR reader initialized with CPU fallback")
                except Exception as e2:
                    logger.error(f"CPU fallback also failed: {str(e2)}")
                    raise Exception(f"Failed to initialize OCR engine: {str(e2)}")
            else:
                raise Exception(f"Failed to initialize OCR engine: {str(e)}")
    
    return _ocr_reader


def preprocess_image(image_path):
    """
    Preprocess image for better OCR accuracy.
    Enhances contrast, sharpness, and removes noise.
    Returns processed image path or original if preprocessing fails.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        
        # Open and convert to RGB if needed
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Enhance contrast (improves text visibility)
        img = ImageEnhance.Contrast(img).enhance(1.2)
        
        # Enhance sharpness (makes text clearer)
        img = ImageEnhance.Sharpness(img).enhance(1.1)
        
        # Apply slight denoising (removes small artifacts)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        # Save processed image temporarily
        base, ext = os.path.splitext(image_path)
        processed_path = f"{base}_processed{ext}"
        img.save(processed_path, quality=95, optimize=True)
        
        logger.info(f"Image preprocessed: {processed_path}")
        return processed_path
    except ImportError:
        logger.warning("PIL not available for preprocessing, using original image")
        return image_path
    except Exception as e:
        logger.warning(f"Image preprocessing failed: {e}, using original image")
        return image_path


def run_ocr(image_path, return_detailed=False):
    """
    Run advanced OCR on an image file with enhanced processing.
    Returns extracted text with bounding box information for better field extraction.
    
    Args:
        image_path: Path to the image file
        return_detailed: If True, returns detailed results with bounding boxes and confidence
        
    Returns:
        str or dict: Extracted text (or detailed dict with bboxes if return_detailed=True)
    """
    try:
        # Check if file exists
        if not os.path.exists(image_path):
            return f"Error: Image file not found at {image_path}"
        
        # Preprocess image for better OCR accuracy
        processed_path = preprocess_image(image_path)
        cleanup_processed = (processed_path != image_path)
        
        try:
            # Get cached reader
            reader = get_ocr_reader()
            
            # Run OCR with detailed results
            logger.info(f"Processing OCR for image: {image_path}")
            try:
                result = reader.readtext(processed_path, detail=1 if return_detailed else 0)
            except Exception as read_error:
                logger.error(f"EasyOCR readtext failed: {str(read_error)}")
                # Try without preprocessing if preprocessing was used
                if cleanup_processed:
                    try:
                        result = reader.readtext(image_path, detail=1 if return_detailed else 0)
                    except Exception as retry_error:
                        raise Exception(f"OCR processing failed: {str(retry_error)}")
                else:
                    raise read_error
            
            # Clean up processed image if created
            if cleanup_processed and os.path.exists(processed_path):
                try:
                    os.remove(processed_path)
                except:
                    pass
            
            if return_detailed:
                # Return detailed results with bounding boxes and confidence
                detailed_results = []
                for item in result:
                    if len(item) >= 3:
                        bbox = item[0]  # Bounding box coordinates
                        text = item[1]  # Extracted text
                        confidence = item[2]  # Confidence score
                        
                        if confidence > 0.3:  # Filter low confidence
                            # Calculate bounding box center and position
                            x_coords = [point[0] for point in bbox]
                            y_coords = [point[1] for point in bbox]
                            center_x = sum(x_coords) / len(x_coords)
                            center_y = sum(y_coords) / len(y_coords)
                            top = min(y_coords)
                            left = min(x_coords)
                            
                            detailed_results.append({
                                'text': text,
                                'confidence': float(confidence),
                                'bbox': bbox,
                                'center_x': center_x,
                                'center_y': center_y,
                                'top': top,
                                'left': left
                            })
                
                return {
                    'text': '\n'.join([r['text'] for r in detailed_results]),
                    'detailed': detailed_results,
                    'total_blocks': len(detailed_results)
                }
            else:
                # Extract text from EasyOCR results (backward compatible)
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
                
        except Exception as ocr_error:
            # Clean up processed image on error
            if cleanup_processed and os.path.exists(processed_path):
                try:
                    os.remove(processed_path)
                except:
                    pass
            raise ocr_error
        
    except ImportError:
        return "OCR engine not installed. Please install easyocr: pip install easyocr"
    except Exception as e:
        error_msg = f"OCR error: {str(e)}"
        logger.error(error_msg)
        return error_msg
