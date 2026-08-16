"""
TeleRAG — Document Metadata parsing.
"""
import re
from typing import Optional
from pydantic import BaseModel


class SpecMetadata(BaseModel):
    specification: str
    version: str
    release: str
    
    
def parse_version_from_filename(filename: str) -> Optional[str]:
    """Extract release/version from 3GPP filename, e.g. 23501-i00.zip -> 18.0.0"""
    # This is a simplistic parse. 
    # i00 -> release 18, subversion 0.0
    match = re.search(r"-([a-z])(\d)(\d)", filename)
    if not match:
        return None
        
    letter, v1, v2 = match.groups()
    
    # a=8, b=9, c=10, d=11, e=12, f=15, g=16, h=17, i=18, j=19
    # Actually, the sequence for releases is:
    # 8=8, 9=9, a=10, b=11, c=12, d=13, e=14, f=15, g=16, h=17, i=18, j=19
    letter_map = {
        '8': 8, '9': 9, 'a': 10, 'b': 11, 'c': 12, 'd': 13, 'e': 14, 
        'f': 15, 'g': 16, 'h': 17, 'i': 18, 'j': 19, 'k': 20
    }
    
    rel = letter_map.get(letter)
    if rel:
        return f"{rel}.{v1}.{v2}"
    return None
