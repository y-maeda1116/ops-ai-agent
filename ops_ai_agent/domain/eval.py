"""golden set に対する triage 精度評価（Eval）のドメインロジック。"""

from pathlib import Path

from pydantic import BaseModel, Field

from ops_ai_agent.domain.models import TriageReport


class GoldenExpectation(BaseModel):
    """golden set 1件の期待値。"""

    severity: str
    cause_keywords: list[str] = Field(default_factory=list)
    action_keywords: list[str] = Field(default_factory=list)


class GoldenCase(BaseModel):
    """golden set 1件（入力ログと期待結果のペア）。"""

    name: str
    log_text: str
    expected: GoldenExpectation


class CaseScore(BaseModel):
    """golden set 1件のスコア。"""

    name: str
    severity_match: bool
    cause_hit_rate: float
    action_hit_rate: float


class EvalSummary(BaseModel):
    """golden set 全体の集計。"""

    total: int
    severity_accuracy: float
    mean_cause_hit_rate: float
    mean_action_hit_rate: float


def load_golden_cases(directory: Path) -> list[GoldenCase]:
    """ディレクトリ配下の *.json から golden set を読み込む。"""
    cases: list[GoldenCase] = []
    for path in sorted(directory.glob("*.json")):
        cases.append(GoldenCase.model_validate_json(path.read_text(encoding="utf-8")))
    return cases


def _keyword_hit_rate(keywords: list[str], texts: list[str]) -> float:
    """キーワードが結合テキストに含まれる割合（大小区別なし）。キーワード無しは満点。"""
    if not keywords:
        return 1.0
    haystack = "\n".join(texts).lower()
    hits = sum(1 for keyword in keywords if keyword.lower() in haystack)
    return hits / len(keywords)


def score_report(report: TriageReport, case: GoldenCase) -> CaseScore:
    """レポートを golden set の期待値と突き合わせて採点する。"""
    return CaseScore(
        name=case.name,
        severity_match=report.severity == case.expected.severity,
        cause_hit_rate=_keyword_hit_rate(
            case.expected.cause_keywords,
            [cause.description for cause in report.possible_causes],
        ),
        action_hit_rate=_keyword_hit_rate(
            case.expected.action_keywords,
            [action.description for action in report.recommended_actions],
        ),
    )


def summarize_eval(scores: list[CaseScore]) -> EvalSummary:
    """スコア群を集計する（空の場合は各指標0）。"""
    total = len(scores)
    if total == 0:
        return EvalSummary(
            total=0,
            severity_accuracy=0.0,
            mean_cause_hit_rate=0.0,
            mean_action_hit_rate=0.0,
        )
    return EvalSummary(
        total=total,
        severity_accuracy=sum(s.severity_match for s in scores) / total,
        mean_cause_hit_rate=sum(s.cause_hit_rate for s in scores) / total,
        mean_action_hit_rate=sum(s.action_hit_rate for s in scores) / total,
    )
