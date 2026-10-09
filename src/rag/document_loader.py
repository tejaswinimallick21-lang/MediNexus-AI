"""
Document Loader for MediNexus AI RAG Knowledge Base.
"""

from pathlib import Path
from typing import List, Dict, Any
from config.constants import DOCUMENTS_DIR


def load_knowledge_documents(docs_dir: Path = DOCUMENTS_DIR) -> List[Dict[str, Any]]:
    """
    Load all synthetic healthcare policy and guideline documents from disk.
    """
    documents = []
    if not docs_dir.exists():
        return documents

    for file_path in docs_dir.glob("**/*.*"):
        if file_path.suffix.lower() in [".txt", ".md"]:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Determine category from parent directory
                category = file_path.parent.name.replace("_", " ").title()

                # Extract title from text if present
                title = file_path.stem.replace("_", " ").title()
                for line in content.splitlines()[:5]:
                    if "DOCUMENT TITLE:" in line:
                        title = line.split("DOCUMENT TITLE:", 1)[1].strip()
                        break

                documents.append({
                    "doc_id": file_path.stem,
                    "filename": file_path.name,
                    "relative_path": str(file_path.relative_to(docs_dir)),
                    "category": category,
                    "title": title,
                    "content": content,
                })
            except Exception as e:
                print(f"Error reading document {file_path}: {e}")

    return documents
