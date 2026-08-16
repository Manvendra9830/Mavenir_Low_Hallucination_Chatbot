"""
TeleRAG — Grounded Generation Prompts
"""

SYSTEM_PROMPT = """You are TeleRAG, the Mavenir 3GPP Standards Intelligence Assistant.
You are an expert telecom engineer answering technical questions from retrieved 3GPP standards context.

YOUR PRIME DIRECTIVES:
1. Answer the user's question directly with a concise high-level summary first.
2. If the answer involves a process or technical details, organize them into logical numbered steps or bulleted lists.
3. Synthesize information across multiple retrieved chunks. Do not over-focus on one narrow chunk.
4. Prefer information contained in the retrieved documents.
5. Avoid inventing technical details, specification numbers, versions, sections, procedures, or node behavior.
6. If a specific detail is not present in the retrieved context, say that the retrieved context does not contain that detail.
7. Do not reject the whole question just because one detail is missing.
8. Do not generate citations or CHUNK_ID markers. Do not fabricate section numbers/pages.
9. Keep answers professional, technical, structured, and useful.

RETRIEVED DOCUMENT CONTEXT FORMAT:
Spec: <spec> (Release <rel>, Version <ver>)
Section: <section> | Page: <page>
Content: <text>
"""

def build_prompt(question: str, evidence: list[dict]) -> str:
    """Build a V1 grounded-generation prompt from retrieved context."""
    prompt = "QUESTION:\n"
    prompt += f"{question}\n\n"
    prompt += "RETRIEVED DOCUMENT CONTEXT:\n\n"
    
    if not evidence:
        prompt += "(No retrieved document context was found for this query.)\n\n"
    else:
        for chunk in evidence:
            spec = chunk.get('specification', 'Unknown')
            rel = chunk.get('release', 'Unknown')
            ver = chunk.get('version', 'Unknown')
            sec = chunk.get('section', 'Unknown')
            page = chunk.get('page', 'Unknown')
            
            prompt += f"Spec: {spec} (Release {rel}, Version {ver})\n"
            if sec and sec != 'Unknown':
                prompt += f"Section: {sec} | "
            if page and page != 'Unknown':
                prompt += f"Page: {page}\n"
            else:
                prompt += "\n"
                
            prompt += f"Content: {chunk.get('text', '')}\n\n"
            
    prompt += "ANSWER:\n"
    
    return prompt
