import pytest

from rubric_grader.rubric import Rubric, RubricError


def test_example_rubric_loads(rubric):
    assert rubric.names == ["concepts", "examples", "clarity"]
    assert rubric.max_total == 100
    assert rubric.assignment.startswith("In 150 to 300 words")


def test_snapshot_round_trips(rubric):
    again = Rubric.from_dict(rubric.snapshot())
    assert again.names == rubric.names
    assert again.max_total == rubric.max_total


def criterion(name="a", points=10):
    return {"name": name, "label": name.upper(), "points": points, "description": "d"}


def test_stated_total_must_match_the_criteria():
    with pytest.raises(RubricError, match="total_points is 100 but the criteria add up to 20"):
        Rubric.from_dict({"criteria": [criterion("a"), criterion("b")], "total_points": 100})


def test_criterion_names_must_be_unique():
    with pytest.raises(RubricError, match="repeated: a"):
        Rubric.from_dict({"criteria": [criterion("a"), criterion("a")]})


@pytest.mark.parametrize("points", [0, -5, 2.5, True, "10"])
def test_points_must_be_a_positive_whole_number(points):
    with pytest.raises(RubricError, match="whole, positive 'points'"):
        Rubric.from_dict({"criteria": [criterion("a", points)]})


@pytest.mark.parametrize("data", [{}, {"criteria": []}, {"criteria": "a"}, []])
def test_rubric_needs_criteria(data):
    with pytest.raises(RubricError):
        Rubric.from_dict(data)
