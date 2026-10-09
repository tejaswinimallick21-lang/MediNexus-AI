"""Ingestion package for MediNexus AI."""
from src.ingestion.ingest_bronze import ingest_bronze_layer
from src.ingestion.synthea_adapter import convert_synthea_to_raw


def generate_healthcare_ecosystem(*args, **kwargs):
    """Legacy synthetic generator (imported lazily: it needs Faker, the Synthea path does not)."""
    from src.ingestion.generate_datasets import generate_healthcare_ecosystem as _generate
    return _generate(*args, **kwargs)
