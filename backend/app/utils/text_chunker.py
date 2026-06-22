from loguru import logger
from ..core.config import settings
import re


def chunk_text(text: str) -> list[str]:
    """
    Split text into overlapping chunks.
    
    Strategy:
    1. Split by natural separators (paragraphs, sentences)
    2. Merge small chunks
    3. Split large chunks at sentence boundaries
    
    Args:
        text: The full text to chunk
        
    Returns:
        List of text chunks
    """
    if not text or not text.strip():
        return []

    # Clean text: normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    chunks = []
    current_chunk = ""
    
    # Split by double newlines first (paragraphs)
    paragraphs = re.split(r'\n\s*\n', text)
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # If adding this paragraph exceeds chunk size, save current and start new
        if len(current_chunk) + len(paragraph) + 1 > settings.CHUNK_SIZE and current_chunk:
            # Try to break at sentence boundary
            split_at = _find_split_point(current_chunk, settings.CHUNK_SIZE)
            if split_at > 0:
                chunks.append(current_chunk[:split_at].strip())
                # Keep overlap text for next chunk
                overlap_start = max(0, split_at - settings.CHUNK_OVERLAP)
                current_chunk = current_chunk[overlap_start:] + " " + paragraph
            else:
                chunks.append(current_chunk.strip())
                current_chunk = paragraph
        else:
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
    
    # Add final chunk
    if current_chunk.strip():
        # If final chunk is too long, split it
        while len(current_chunk) > settings.CHUNK_SIZE:
            split_at = _find_split_point(current_chunk, settings.CHUNK_SIZE)
            if split_at > 0:
                chunks.append(current_chunk[:split_at].strip())
                overlap_start = max(0, split_at - settings.CHUNK_OVERLAP)
                current_chunk = current_chunk[overlap_start:]
            else:
                chunks.append(current_chunk[:settings.CHUNK_SIZE].strip())
                current_chunk = current_chunk[settings.CHUNK_SIZE:]
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
    
    # Filter out any empty chunks
    chunks = [c for c in chunks if c and len(c) > 10]
    
    logger.info(f"Text chunked into {len(chunks)} chunks (chunk_size={settings.CHUNK_SIZE}, overlap={settings.CHUNK_OVERLAP})")
    return chunks


def _find_split_point(text: str, target_size: int) -> int:
    """
    Find a good split point near target_size.
    Prefers sentence boundaries (。！？.!?), then paragraph breaks.
    """
    if len(text) <= target_size:
        return len(text)
    
    # Search for Chinese/English sentence boundaries near target_size
    search_start = max(target_size - 100, 0)
    search_end = min(target_size + 100, len(text))
    search_region = text[search_start:search_end]
    
    # Priority 1: Sentence-ending punctuation (Chinese and English)
    for sep in ["。", "！", "？", "\n", ". ", "! ", "? "]:
        pos = search_region.rfind(sep, 0, len(search_region))
        if pos > 0:
            return search_start + pos + len(sep)
    
    # Priority 2: Comma or other punctuation
    for sep in ["，", "；", ", ", "; "]:
        pos = search_region.rfind(sep, 0, len(search_region))
        if pos > 0:
            return search_start + pos + len(sep)
    
    # Priority 3: Just split at target_size
    return target_size