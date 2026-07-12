"""Central configuration loaded from environment / .env.

No keys are required for the seeded demo. Each integration reads its keys here
and degrades gracefully when they are absent (see the `*_enabled` helpers).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (backend/app/config.py -> repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), extra="ignore", case_sensitive=False
    )

    # LLM — provider selection (amd = primary: Gemma on the AMD MI300X)
    llm_provider: str = "amd"  # amd | gemini

    # Speed-race GPU baseline (right-hand side): auto | gemini (Gemma on Google's GPU)
    race_baseline: str = "auto"

    # Gemma on the AMD MI300X via Ollama (ROCm), OpenAI-compatible. Set
    # AMD_LLM_BASE_URL to the Ollama endpoint (…/v1); reasoning on gemma4:31b
    # (thinking mode), vision on gemma3:12b.
    amd_llm_base_url: str = ""
    amd_llm_api_key: str = "ollama"
    amd_llm_model: str = "gemma4:31b"
    amd_llm_vision_model: str = "gemma3:12b"

    # Google (GPU baseline for the speed race — OpenAI-compatible endpoint).
    # Default is Gemma 4 31B served by Google = the SAME Gemma we serve on AMD,
    # so the race is apples-to-apples (hardware is the only variable).
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemma-4-31b-it"
    gemini_vision_model: str = "gemma-4-31b-it"

    # Data mode
    live_mode: bool = False
    # In live mode also auto-derive the PAID Bright Data sources (Medium, lablab) from
    # the handle. Off by default so live runs don't spend credits unprompted;
    # explicitly-provided Medium/LinkedIn/lablab URLs are always queried.
    live_try_paid_sources: bool = False

    # Database backend. Set DATABASE_URL to a Google Cloud SQL for PostgreSQL endpoint
    # (with pgvector) to use Cloud SQL as the store + vector search.
    # When unset, the store is in-memory (the pipeline holds the full working set).
    database_url: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # GitHub
    github_token: str = ""

    # Google Maps — client-side (referrer-restricted) key for the candidate Map
    # view. Absent → the Map view falls back to keyless per-candidate embeds.
    google_maps_api_key: str = ""

    # Bright Data Web Unlocker — primary unblock layer for bot-protected sources
    # (LinkedIn, Medium, lablab). Returns rendered HTML past blocks/Cloudflare.
    brightdata_api_token: str = ""
    brightdata_zone: str = "web_unlocker1"          # the Web Unlocker zone name
    brightdata_url: str = "https://api.brightdata.com/request"

    # Ollama embeddings (e.g. all-minilm served by Ollama on the AMD MI300X). When
    # set, embeddings run on that Ollama GPU endpoint. all-minilm is 384-dim, so it
    # matches embedding_dim + the pgvector(384) column.
    ollama_embeddings_url: str = ""
    ollama_embeddings_model: str = "all-minilm"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Video
    video_output_dir: str = "video/out"
    tts_enabled: bool = True
    # macOS `say` narration voice + rate. Samantha is a clear, professional voice
    # (far better than the robotic default). Install "Enhanced"/Siri voices in
    # System Settings → Accessibility → Spoken Content for near-human quality.
    tts_voice: str = "Samantha"
    tts_rate: int = 178  # words per minute
    # Pre-generated "featured" video reused everywhere so we never pay to render
    # again. Set FEATURED_VIDEO="" to fall back to per-analysis generated videos.
    featured_video: str = "video/out/featured.mp4"

    # Visual Portfolio — each image costs one Gemma vision call, so these two bound
    # the slowest agent. Lower the cap (or raise concurrency) to speed a run up.
    visual_max_images: int = 4
    visual_concurrency: int = 4

    # OpenUI (frontend generation — used at build time, flag for reporting)
    openui_enabled: bool = True

    # --- capability helpers ---
    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def brightdata_enabled(self) -> bool:
        return bool(self.brightdata_api_token and self.brightdata_zone)

    @property
    def ollama_embeddings_enabled(self) -> bool:
        return bool(self.ollama_embeddings_url)

    @property
    def amd_llm_enabled(self) -> bool:
        return bool(self.amd_llm_base_url)

    @property
    def llm_enabled(self) -> bool:
        """Any chat provider configured → real LLM calls (heuristic fallback otherwise)."""
        return bool(self.amd_llm_enabled or self.gemini_enabled)

    @property
    def active_provider(self) -> str:
        """Resolve the configured provider, falling back to whatever key is present."""
        preferred = (self.llm_provider or "amd").lower()
        avail = {
            "amd": self.amd_llm_enabled,
            "gemini": self.gemini_enabled,
        }
        if avail.get(preferred):
            return preferred
        for name, ok in avail.items():  # amd → gemini
            if ok:
                return name
        return "none"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def featured_video_path(self) -> Path:
        p = Path(self.featured_video)
        return p if p.is_absolute() else (REPO_ROOT / self.featured_video)

    @property
    def featured_video_enabled(self) -> bool:
        return bool(self.featured_video) and self.featured_video_path.exists()

    @property
    def db_backend(self) -> str:
        """Active persistence backend: postgres (Cloud SQL) | memory."""
        return "postgres" if self.database_url else "memory"

    @property
    def demo_data_dir(self) -> Path:
        return REPO_ROOT / "demo_data"

    @property
    def video_out_path(self) -> Path:
        p = REPO_ROOT / self.video_output_dir
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
