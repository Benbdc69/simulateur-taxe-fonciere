"""Pistes indicatives pour la 6660-REV à partir de la NAF rév. 2."""
import re

BUREAUX = ('BUR1', 'BUR2', 'BUR3')
COMMERCES = ('MAG1', 'MAG2', 'MAG3', 'MAG4', 'MAG5')

# Les exceptions affinent les activités pour lesquelles la division seule est trop large.
PAR_CODE = {
    '4520A': ('ATE1', 'ATE2'),
    '4520B': ('ATE1', 'ATE2'),
    '4730Z': ('MAG6',),
    '5221Z': ('DEP3', 'DEP4'),
    '5510Z': ('HOT1', 'HOT2', 'HOT3'),
    '5520Z': ('HOT4', 'HOT5'),
    '5530Z': ('SPE4', 'SPE5'),
    '6831Z': ('MAG1', *BUREAUX),
    '8610Z': ('CLI1',),
    '9311Z': ('SPE2',),
    '9313Z': ('SPE2',),
    '9602A': ('MAG1', 'MAG2', 'MAG3'),
    '9602B': ('MAG1', 'MAG2', 'MAG3'),
    '9604Z': ('SPE6', 'MAG1'),
}

PAR_DIVISION = {
    '46': ('DEP2', 'DEP1', 'DEP5', *BUREAUX),
    '47': COMMERCES,
    '52': ('DEP2', 'DEP1', 'DEP5', *BUREAUX),
    '56': ('MAG1', 'MAG2', 'MAG3'),
    **dict.fromkeys(('58', '62', '63', '64', '65', '66', '69', '70', '71', '73', '74', '82'), BUREAUX),
    '85': ('ENS1', 'ENS2'),
    '86': ('CLI2', 'CLI4', *BUREAUX),
    '87': ('CLI3', 'CLI2'),
    '88': ('CLI2', *BUREAUX),
    '90': ('SPE1', 'SPE3'),
    '93': ('SPE2', 'SPE3', 'SPE7'),
    '95': ('ATE1', 'ATE2'),
}


def categories_suggerees(ape):
    """Renvoie des pistes, sans valider l’existence du code ni classer le local."""
    code = re.sub(r'\s+', '', ape).upper()
    if not re.fullmatch(r'\d{2}\.?\d{2}[A-Z]', code, re.ASCII):
        raise ValueError('Saisissez un code APE au format 47.11D ou 4711D.')
    code = code.replace('.', '')
    return PAR_CODE.get(code, PAR_DIVISION.get(code[:2], ()))
