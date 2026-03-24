import dataclasses
from typing import Optional


@dataclasses.dataclass
class ExportAssetActivityInputs:
    exported_asset_id: int
    source: Optional[str] = None


@dataclasses.dataclass
class ExportError:
    exception_class: str
    error_trace: str = ""


@dataclasses.dataclass
class ExportAssetResult:
    exported_asset_id: int
    success: bool
    error: Optional[ExportError] = None
    insight_id: Optional[int] = None
    duration_ms: Optional[float] = None
    export_format: str = ""
    attempts: int = 1
