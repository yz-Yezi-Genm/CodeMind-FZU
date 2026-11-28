"""Test-only FastAPI entry for student browser checks without a model key."""
from backend.app.alpha import create_alpha_app
from backend.app.config import AppSettings, PROJECT_ROOT
from backend.services.alpha_runtime import build_alpha_runtime
from scripts.check_retrieval_agent import FirstEvidenceLLM


settings = AppSettings(alpha_package_dir=PROJECT_ROOT / "tests/fixtures/beta_live_synthetic")


async def build_runtime():
    return await build_alpha_runtime(settings, llm_client=FirstEvidenceLLM())


app = create_alpha_app(settings=settings, runtime_builder=build_runtime)
