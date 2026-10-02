import pytest

from app.services.checkout_service import CheckoutError, CheckoutService


@pytest.mark.parametrize(
    "nome,email,cpf,field",
    [
        ("A", "a@b.com", "52998224725", "nome"),
        ("Maria Souza", "nope", "52998224725", "email"),
        ("Maria Souza", "a@b.com", "5299822472", "cpf"),  # 10 digits
        ("Maria Souza", "a@b.com", "529.982.247-26", "cpf"),  # bad check digit
        ("Maria Souza", "a@b.com", "00000000000", "cpf"),  # repdigit
        ("Maria Souza", "a@b.com", "", "cpf"),
    ],
)
def test_validate_buyer_rejects(nome, email, cpf, field):
    with pytest.raises(CheckoutError) as exc:
        CheckoutService.validate_buyer(nome, email, cpf)
    assert exc.value.status_code == 422 and exc.value.field == field


def test_validate_buyer_normalizes():
    assert CheckoutService.validate_buyer("  Maria Souza ", "Maria@GMAIL.com", "529.982.247-25") == (
        "Maria Souza", "maria@gmail.com", "52998224725",
    )
