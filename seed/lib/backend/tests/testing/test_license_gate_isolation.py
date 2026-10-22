"""The pytest plugin isolates the process-global license gate between tests (order-independence)."""
from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate, get_license_gate


def test_a_test_configuring_the_gate_installs_it():
    assert get_license_gate() is None
    configure_license_gate("leaky", FakeLicenseChecker(allow_all=False))
    assert get_license_gate() is not None


def test_the_gate_does_not_leak_into_the_next_test_in_either_order():
    # Passes after the test above in file order AND under pytest-randomly's shuffle: the autouse
    # snapshot/restore fixture removes whatever the other test installed.
    assert get_license_gate() is None
