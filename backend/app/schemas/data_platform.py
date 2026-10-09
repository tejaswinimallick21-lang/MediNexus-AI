"""Schemas for the Data Engineering workspace: upload sandbox, cleaning report and ML insights."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

UploadStatus = Literal["processing", "ready", "failed"]


class CleaningStep(BaseModel):
    step: str
    detail: str
    affected: int
    note: Optional[str] = None


class ColumnInfo(BaseModel):
    name: str
    kind: str
    missing_pct: float
    unique: int
    pii_masked: bool
    example: Optional[str] = None


class Quality(BaseModel):
    completeness: float
    validity: float
    uniqueness: float
    consistency: float
    overall: float


class CleaningReport(BaseModel):
    rows_in: int
    rows_out: int
    steps: List[CleaningStep]
    columns: List[ColumnInfo]
    quality: Quality


class HistogramBin(BaseModel):
    bin: str
    count: int


class NumericSummary(BaseModel):
    column: str
    mean: float
    std: float
    min: float
    p25: float
    median: float
    p75: float
    max: float
    missing_pct: float
    extreme_outliers: int
    histogram: List[HistogramBin]


class CategoryValue(BaseModel):
    value: str
    count: int
    share_pct: float


class CategorySummary(BaseModel):
    column: str
    distinct: int
    top: List[CategoryValue]


class Correlation(BaseModel):
    a: str
    b: str
    rho: float


class Segment(BaseModel):
    cluster: int
    size: int
    share_pct: float
    traits: List[str]


class Segments(BaseModel):
    available: bool
    reason: Optional[str] = None
    rows_used: Optional[int] = None
    k: Optional[int] = None
    silhouette: Optional[float] = None
    structure: Optional[str] = None
    clusters: List[Segment] = []
    anomaly_share_pct: Optional[float] = None
    anomalies: Optional[int] = None


class DriftColumn(BaseModel):
    column: str
    upload_median: float
    lakehouse_median: float
    psi: float
    shift: str


class Drift(BaseModel):
    available: bool
    reason: Optional[str] = None
    reference_table: Optional[str] = None
    columns: List[DriftColumn] = []


class DateCoverage(BaseModel):
    column: str
    start: str
    end: str


class Profile(BaseModel):
    rows: int
    columns: int
    numeric: List[NumericSummary]
    categories: List[CategorySummary]
    correlations: List[Correlation]
    date_coverage: Optional[DateCoverage] = None
    segments: Segments
    drift: Drift


class ExcludedColumn(BaseModel):
    column: str
    reason: str


class Driver(BaseModel):
    feature: str
    importance: float


class Prediction(BaseModel):
    target: str
    task: Literal["classification", "regression"]
    rows_used: int
    train_rows: int
    test_rows: int
    split: str
    features_used: List[str]
    excluded: List[ExcludedColumn]
    primary_metric: str
    score: float
    baseline_score: float
    baseline_label: str
    beats_baseline: bool
    verdict: str
    drivers: List[Driver]
    classes: Optional[int] = None
    accuracy: Optional[float] = None
    baseline_accuracy: Optional[float] = None
    macro_f1: Optional[float] = None
    roc_auc: Optional[float] = None
    positive_class: Optional[str] = None
    mae: Optional[float] = None
    baseline_mae: Optional[float] = None
    r2: Optional[float] = None


class SeriesPoint(BaseModel):
    date: str
    value: float


class Forecast(BaseModel):
    date_column: str
    value_column: Optional[str] = None
    aggregation: str
    frequency: Literal["daily", "weekly"]
    horizon: int
    history_points: int
    backtest_folds: int
    model_mae: float
    baseline_mae: float
    baseline_label: str
    serving_method: Literal["model", "baseline"]
    skill_pct: float
    history: List[SeriesPoint]
    forecast: List[SeriesPoint]
    next_total: float
    last_total: float


class UploadSummary(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    sha256: str
    uploaded_by: str
    created_at: str
    status: UploadStatus
    stage: str
    rows: Optional[int] = None
    columns: Optional[int] = None
    quality_score: Optional[float] = None


class UploadDetail(UploadSummary):
    error: Optional[str] = None
    job_id: Optional[str] = None
    cleaning: Optional[CleaningReport] = None
    profile: Optional[Profile] = None
    predictions: List[Prediction] = []
    forecast: Optional[Forecast] = None
    summary: List[str] = []
    preview_columns: List[str] = []
    preview_rows: List[List[Optional[str]]] = []


class UploadAccepted(BaseModel):
    upload: UploadSummary
    job_id: str


class JobAccepted(BaseModel):
    job_id: str


class PredictIn(BaseModel):
    target: str = Field(..., min_length=1, max_length=120)


class ForecastIn(BaseModel):
    date_column: str = Field(..., min_length=1, max_length=120)
    value_column: Optional[str] = Field(None, max_length=120, description="Omit to forecast the number of rows per period")
    aggregation: Literal["sum", "mean"] = "sum"
