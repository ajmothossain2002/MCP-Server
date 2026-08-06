"""
Reusable parsers for extracting structured data and code from LLM responses.
"""
import json
import re
import yaml
from typing import List, Dict, Any, Optional

from shared.response import CodeArtifact

def extract_code_blocks(text: str, language: Optional[str] = None) -> List[CodeArtifact]:
    """
    Extracts Markdown fenced code blocks from text.
    
    Args:
        text (str): The markdown text containing code blocks.
        language (Optional[str]): If provided, only extracts blocks for this specific language.
        
    Returns:
        List[CodeArtifact]: A list of parsed code artifacts.
    """
    # Regex to match ```language\n...content...\n```
    pattern = re.compile(r"```([\w+-]*)\n(.*?)```", re.DOTALL)
    matches = pattern.findall(text)
    
    artifacts = []
    for lang, content in matches:
        lang = lang.strip().lower()
        if language and lang != language.lower():
            continue
        artifacts.append(CodeArtifact(
            language=lang or "text",
            content=content.strip()
        ))
    return artifacts

def parse_json(text: str) -> Dict[str, Any]:
    """
    Extracts and parses JSON from text, handling potential Markdown fencing.
    
    Args:
        text (str): Text potentially containing a JSON block.
        
    Returns:
        Dict[str, Any]: Parsed JSON dictionary.
    """
    # If the response is wrapped in ```json ... ```, extract it
    blocks = extract_code_blocks(text, language="json")
    json_text = blocks[0].content if blocks else text.strip()
    
    # Strip potential non-JSON prefix/suffix if the LLM got chatty
    start_idx = json_text.find('{')
    end_idx = json_text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_text = json_text[start_idx:end_idx+1]
        
    return json.loads(json_text)

def parse_yaml(text: str) -> Dict[str, Any]:
    """
    Extracts and parses YAML from text.
    
    Args:
        text (str): Text potentially containing a YAML block.
        
    Returns:
        Dict[str, Any]: Parsed YAML dictionary.
    """
    blocks = extract_code_blocks(text, language="yaml")
    yaml_text = blocks[0].content if blocks else text.strip()
    return yaml.safe_load(yaml_text)
