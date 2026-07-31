"""Application configuration from environment variables.

Configuration for the Video Agent Context Graph: Neo4j (bolt) for the graph,
an OpenAI-brained Strands agent, and TwelveLabs (Marengo + Pegasus) for video
understanding. Short-term chat context is kept in-process (see app.memory).
"""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from the repo-root .env file."""

    # --- Neo4j (self-hosted, bolt) -----------------------------------------
    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # --- OpenAI (agent reasoning + structured video extraction) ------------
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6"
    openai_extraction_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"

    # --- TwelveLabs (video understanding) ----------------------------------
    # The SDK auto-reads TWELVE_LABS_API_KEY from the environment; this mirror
    # lets us fail fast with a clear message and pass it explicitly if needed.
    twelve_labs_api_key: str = ""
    # Reuse an existing index by id, or let ingestion create/find one by name.
    tl_index_id: str = ""
    tl_index_name: str = "video-context-graph"
    # Model version strings — config-driven so they can be bumped.
    marengo_model: str = "marengo3.0"          # search/index model on the index
    pegasus_model: str = "pegasus1.2"          # analyze/generate model (index accepts pegasus1.2)
    marengo_embed_model: str = "marengo3.0"  # embed.create model (verified live: 512-dim text embeddings)

    # --- Long-video analysis -----------------------------------------------
    # A single analyze call is capped at 4096 output tokens, which silently
    # truncates anything past a few minutes (an 18-minute clip came back
    # covering only its first third). Videos longer than the window are
    # analyzed one window at a time and stitched back into one Video node.
    # Windowing needs the window-capable Pegasus, which addresses the video by
    # asset id instead of index video id; TwelveLabs returns the same value for
    # both, so no re-upload is involved.
    pegasus_window_model: str = "pegasus1.5"
    # Smaller windows keep long recordings from collapsing several minutes of
    # distinct speakers, teams, and locations into one oversized graph segment.
    analysis_window_sec: int = 120
    analysis_max_tokens: int = 4096            # hard API ceiling for this model
    analysis_concurrency: int = 3              # windows analyzed in parallel

    # --- Large file upload --------------------------------------------------
    # tasks.create posts the whole file in a single request, which is a poor bet
    # for multi-gigabyte captures: one dropped connection loses the entire
    # transfer. Files at or above this size are cut into parts and uploaded a
    # part at a time, with per-part retries, so a failure costs one part.
    multipart_threshold_mb: int = 200
    upload_chunk_workers: int = 5              # parts uploaded in parallel
    index_timeout_sec: int = 3600
    # Neo4j vector index dimension — must match the embed model. The ingest
    # script discovers the true dimension from the first embedding and creates
    # the index accordingly; this is only the default/hint.
    embedding_dimensions: int = 512

    # Public sample clip(s) to ingest when none are supplied. Comma-separated.
    # Big Buck Bunny 720p is the license-clean fallback known to pass TwelveLabs
    # validation; swap in your own clips via SAMPLE_VIDEO_URLS in .env.
    sample_video_urls: str = (
        "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_5MB.mp4"
    )

    # --- App ----------------------------------------------------------------
    domain_id: str = "video-context-graph"
    backend_port: int = 8000
    frontend_port: int = 3000
    # Comma-separated browser origins allowed to call the API. Empty means "just
    # the Next.js frontend on frontend_port".
    cors_origins: str = ""

    # --- Headshots (lazy, on demand) ----------------------------------------
    # Generated on first GET /api/entities/{key}/headshot and cached in Neo4j +
    # on disk under static/headshots/. The frame from the HLS playback at the
    # first segment that mentions the person is sent to OpenAI's image-edit
    # endpoint with a "professional headshot" instruction; the result is what
    # gets served.
    headshot_static_dir: str = "../static/headshots"
    headshot_url_prefix: str = "/static/headshots"
    headshot_openai_model: str = "gpt-image-1"
    headshot_prompt: str = (
        "Turn this video frame into a polished professional headshot of the "
        "person shown. Keep their identity (face, hair, skin tone, age) "
        "recognizable. Replace the background with a clean, soft studio "
        "backdrop (subtle gradient, neutral color). Use flattering, even "
        "studio lighting and frame the subject from the chest up, centered, "
        "looking toward the camera with a natural confident expression. Do "
        "not change clothing unless it is clearly casual; otherwise preserve "
        "what they are wearing. Photorealistic, high resolution."
    )

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def sample_video_url_list(self) -> list[str]:
        return [u.strip() for u in self.sample_video_urls.split(",") if u.strip()]


settings = Settings()
