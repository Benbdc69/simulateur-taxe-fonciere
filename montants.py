"""Format d’affichage des montants de synthèse."""
from decimal import Decimal, ROUND_FLOOR


def euro_arrondi(montant):
    """Arrondit à l’euro supérieur à partir de 0,50."""
    valeur = Decimal(str(montant))
    entier = valeur.to_integral_value(rounding=ROUND_FLOOR)
    if valeur - entier >= Decimal('0.50'):
        entier += 1
    return f'{int(entier):,}'.replace(',', ' ') + ' €'
