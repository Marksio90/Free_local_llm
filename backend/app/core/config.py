from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://ollama:11434"
    chroma_url: str = "http://chromadb:8000"
    github_token: str = ""
    embed_model: str = "nomic-embed-text"
    default_model: str = "qwen3:4b"  # bezpieczny default – docker-compose go pobiera przy starcie

    # Lekki model do zadań w tle (generowanie datasetu, klasyfikacja zapytań)
    # Zajmuje ~1 GB RAM — nie koliduje z głównym modelem podczas czatu
    background_model: str = "qwen2.5:1.5b"

    # Tryb laptopa: wyłącza LoRA training, zmniejsza równoległość
    laptop_mode: bool = False

    data_dir: str = "/app/data"
    repos_dir: str = "/app/repos"
    training_output_dir: str = "/app/training/output"

    model_config = {"env_file": ".env"}


settings = Settings()
