"""組み込みエージェントの登録"""

from __future__ import annotations

from ..agent import BaseAgent
from .audio_pack import AudioPackAgent
from .image_variants import ImageVariantsAgent
from .listing_writer import ListingWriterAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "audio_pack": AudioPackAgent,
    "image_variants": ImageVariantsAgent,
    "listing_writer": ListingWriterAgent,
}
