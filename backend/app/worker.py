"""Dedicated document-processing worker entry point."""

from app.services.document_processing import run_worker

if __name__ == "__main__":
    run_worker()
