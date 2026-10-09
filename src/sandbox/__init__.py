"""
Upload sandbox: an isolated Bronze → Silver → Gold run and ML insights for one uploaded file.

Nothing here writes to data/raw or the live lakehouse database; every artefact lives under
data/uploads/<upload_id>/. Promotion into the live lakehouse is a separate, approved step.
"""
