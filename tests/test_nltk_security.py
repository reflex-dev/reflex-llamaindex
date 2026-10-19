"""Guard the model-artifact path checks covered by GHSA-8mgp-746c-j5xp."""

from pathlib import Path
from tempfile import TemporaryDirectory

import nltk.data
import numpy as np
import pytest
from nltk import pathsec
from nltk.classify.maxent import save_maxent_params
from nltk.tag.perceptron import AveragedPerceptron, PerceptronTagger


@pytest.mark.parametrize("operation", ["save", "load", "tagger", "maxent"])
def test_model_artifact_paths_cannot_escape_allowed_roots(
    operation, tmp_path, monkeypatch
):
    """Reject outside-root model reads and writes before touching the target."""
    monkeypatch.setattr(pathsec, "ENFORCE", True)
    monkeypatch.setattr(nltk.data, "path", [str(tmp_path)])
    monkeypatch.setattr(pathsec, "_ALLOWED_ROOTS_CACHE", None)
    monkeypatch.setattr(pathsec, "_LAST_DATA_PATHS", None)
    with TemporaryDirectory(prefix=".reflex-nltk-test-", dir=Path.home()) as outside:
        target = Path(outside) / "weights.json"
        target.write_text("{}")
        with pytest.raises(PermissionError):
            pathsec.open(str(target), "r")
        with pytest.raises(PermissionError):
            if operation == "save":
                AveragedPerceptron().save(str(target))
            elif operation == "load":
                AveragedPerceptron().load(str(target))
            elif operation == "tagger":
                PerceptronTagger(load=False).save_to_json(loc=outside)
            else:
                save_maxent_params(np.array([]), {}, [], {}, tab_dir=outside)
        assert target.read_text() == "{}"
        assert sorted(p.name for p in Path(outside).iterdir()) == ["weights.json"]
