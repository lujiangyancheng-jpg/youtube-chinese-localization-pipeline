from __future__ import annotations

from youtube_localizer.translation.glossary import glossary_consistency_issues, load_glossary


def test_load_glossary_and_consistency(tmp_path) -> None:
    path = tmp_path / "glossary.yaml"
    path.write_text("terms:\n  Kubernetes: Kubernetes\n  cloud: 云\n", encoding="utf-8")
    glossary = load_glossary(path)
    assert glossary["cloud"] == "云"
    issues = glossary_consistency_issues(
        ["A cloud service", "Kubernetes cluster"],
        ["一项服务", "Kubernetes 集群"],
        glossary,
    )
    assert len(issues) == 1
    assert "cloud" in issues[0]
