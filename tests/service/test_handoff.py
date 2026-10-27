"""Handing a ready batch to slim-data (P-11, P-12; slim-data D-95)."""

from decimal import Decimal

import pytest
from slim_data.domain.actor import Actor as ResultsActor
from slim_data.domain.enums import IdentitySource, ReadingRole
from slim_data.domain.enums import Role as ResultsRole
from slim_data.persistence import migrate as results_migrate
from slim_data.persistence.observations import get_batch as results_get_batch

from slim_prep.domain.prep import CupFigures, CupKind, figures
from slim_prep.domain.problems import PrepRefused
from slim_prep.persistence import books
from slim_prep.persistence.rules import publish_rules
from slim_prep.service.handoff import results_batch, send_to_results, sent_version
from tests.factories import ANALYST, QUALITY, RULES, batch, chain, conc

RESULTS_ANA = ResultsActor(
    id="ana-1",
    display="Ana",
    roles=frozenset({ResultsRole.ANALYST}),
    identity_source=IdentitySource.AUTHENTICATED,
)
METALS = ("Cu", "Fe")  # the analysis measures Cu and Fe; the standard also has Ni


def test_samples_spikes_and_dilutions_in_slim_datas_shape():
    sent = results_batch(batch(), figures(batch(), RULES), 7, METALS, "ppb")
    assert sent.code == "PB-0001" and sent.analysis_id == 7 and sent.prep_method == "evaporation"
    assert [str(s) for s in sent.samples] == ["TR00042-01"]
    assert [(s.analyte.code, s.added.value, s.added.unit) for s in sent.spikes] == [
        ("Cu", Decimal("0.05"), "ppb"),
        ("Fe", Decimal("0.05"), "ppb"),
    ]
    assert [(d.role, d.replicate, d.dilution) for d in sent.dilutions] == [
        (ReadingRole.CUP, 1, Decimal("0.06")),
        (ReadingRole.CUP, 2, Decimal("0.06")),
        (ReadingRole.SPIKE, 1, Decimal("0.06")),
    ]


def test_a_unit_slim_prep_cant_express_is_refused():
    with pytest.raises(PrepRefused, match="can't be given in '%'"):
        results_batch(batch(), figures(batch(), RULES), 7, METALS, "%")


def test_one_spike_amount_per_sample_and_element():
    def spike_cup(n):
        return CupFigures(
            sample="TR00042-01", cup=n, kind=CupKind.SPIKE, net=Decimal(10), solution=Decimal(1),
            dilution=Decimal("0.1"), added=(("Cu", conc("50", "ppt")),),
        )  # fmt: skip

    with pytest.raises(PrepRefused, match="Cu is spiked in two cups"):
        results_batch(batch(), (spike_cup(3), spike_cup(4)), 7, METALS, "ppb")


@pytest.fixture
def recorded(session):
    results_migrate.upgrade(session.connection())
    rules_id = publish_rules(session, RULES, QUALITY).id
    for standard in chain():
        books.save_standard(session, standard, rules_id, ANALYST)
    books.save_batch(session, batch(), rules_id, ANALYST)
    return session


def test_send_registers_the_batch_in_slim_data_once(recorded):
    session = recorded
    assert sent_version(session, "PB-0001") is None
    send_to_results(session, "PB-0001", RESULTS_ANA, 7, METALS, "ppb")
    stored = results_get_batch(session, "PB-0001")
    assert len(stored.dilutions) == 3 and stored.spike_added(stored.samples[0], stored.spikes[0].analyte)
    assert sent_version(session, "PB-0001") == 1
    with pytest.raises(PrepRefused, match="already sent"):
        send_to_results(session, "PB-0001", RESULTS_ANA, 7, METALS, "ppb")
