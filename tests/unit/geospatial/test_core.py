import math

import numpy as np
import pytest

from raahat.domain.geospatial.asr_sim import corrupt
from raahat.domain.geospatial.channel import ChannelModel, NaiveChannel, NameIndex, levenshtein
from raahat.domain.geospatial.engine import LocationEngine
from raahat.domain.geospatial.events import Envelope, location_updated
from raahat.domain.geospatial.gazetteer import City
from raahat.domain.geospatial.geo import Grid, box_sum
from raahat.domain.geospatial.probe import evaluate, strip_template
from raahat.domain.geospatial.simulate import run_episode


@pytest.fixture(scope="module")
def city() -> City:
    return City(seed=3)


@pytest.fixture(scope="module")
def channel(city: City) -> ChannelModel:
    rng = np.random.default_rng(0)
    pairs = [(n, corrupt(n, 0.15, rng)) for n in city.names for _ in range(20)]
    return ChannelModel.learn(pairs)


def test_box_sum_matches_bruteforce() -> None:
    rng = np.random.default_rng(1)
    n, r = 9, 2
    p = rng.random(n * n)
    a = p.reshape(n, n)
    brute = np.array(
        [
            a[max(i - r, 0) : i + r + 1, max(j - r, 0) : j + r + 1].sum()
            for i in range(n)
            for j in range(n)
        ]
    )
    assert np.allclose(box_sum(p, n, r), brute)


def test_grid_index_roundtrip() -> None:
    g = Grid(600, 60)
    assert g.ncells == 100 and g.index_of((5, 5)) == 0 and g.index_of((599, 599)) == 99


def test_levenshtein_and_zero_noise() -> None:
    assert levenshtein("kitten", "sitting") == 3
    assert corrupt("shiv mandir", 0.0, np.random.default_rng(0)) == "shiv mandir"


def test_corrupt_is_deterministic_per_seed() -> None:
    a = corrupt("shiv mandir", 0.3, np.random.default_rng(5))
    b = corrupt("shiv mandir", 0.3, np.random.default_rng(5))
    assert a == b


def test_learned_channel_resolves_noisy_names(city: City, channel: ChannelModel) -> None:
    rng = np.random.default_rng(42)
    idx = NameIndex(city.names, channel)
    hits = 0
    total = 150
    for _ in range(total):
        n = city.names[int(rng.integers(len(city.names)))]
        s = idx.scores(corrupt(n, 0.15, rng))
        hits += city.names[int(np.argmax(s))] == n
    assert hits / total > 0.85


def test_naive_channel_prefers_exact() -> None:
    c = NaiveChannel()
    assert c.loglik("shiv mandir", "shiv mandir") > c.loglik("shiv mandir", "ram mandir")


def test_mention_concentrates_belief_near_named_landmarks(
    city: City, channel: ChannelModel
) -> None:
    eng = LocationEngine(city, channel)
    name = city.names[0]
    eng.observe(("mention", name))
    ids = city.name_to_idx[name]
    d = np.sqrt(((city.grid.centers[:, None, :] - city.xy[ids][None]) ** 2).sum(-1)).min(1)
    assert eng.p[d <= 400].sum() > 0.8


def test_questions_improve_localisation(city: City, channel: ChannelModel) -> None:
    first = [run_episode(city, channel, "none", 0.15, seed=i) for i in range(20)]
    asked = [run_episode(city, channel, "landmark", 0.15, seed=i) for i in range(20)]
    assert np.median([r["err_m"] for r in asked]) < 0.25 * np.median([r["err_m"] for r in first])


def test_ward_value_is_bounded(city: City, channel: ChannelModel) -> None:
    eng = LocationEngine(city, channel, utility="entropy")
    assert 0 <= eng.eig(("ward",)) <= math.log(len(city.ward_names)) + 1e-9
    eng2 = LocationEngine(city, channel, utility="conf")
    assert 0 <= eng2.eig(("ward",)) <= 1.0


def test_question_values_are_finite(city: City, channel: ChannelModel) -> None:
    eng = LocationEngine(city, channel, seed=1)
    eng.observe(("mention", city.names[3]))
    for q in eng.candidate_questions():
        assert np.isfinite(eng.eig(q))


def test_episode_deterministic(city: City, channel: ChannelModel) -> None:
    a = run_episode(city, channel, "adaptive", 0.15, seed=7)
    b = run_episode(city, channel, "adaptive", 0.15, seed=7)
    assert a == b


def test_events_roundtrip() -> None:
    e = location_updated("call1", (10.0, 20.0), 0.8, 3.2, ["landmark"])
    e2 = Envelope.from_json(e.to_json())
    assert e2.id == e.id and e2.data["confidence"] == 0.8


def test_probe_selftest_and_strip() -> None:
    assert strip_template("shiv mandir ke paas hoon") == "shiv mandir"
    rng = np.random.default_rng(0)
    c = City(seed=3)
    pairs = [(n, corrupt(n, 0.15, rng)) for n in c.names for _ in range(6)]
    r = evaluate(pairs, c.names)
    assert r["learned_top1"] > 0.8
