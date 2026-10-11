"""Evidence-grounded document review with a local Ollama model."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("medical-approval")
except PackageNotFoundError:
    __version__ = "0.0.0+local"
