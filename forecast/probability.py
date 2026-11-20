from collections.abc import Mapping
from fractions import Fraction


def fraction_payload(value: Fraction) -> dict[str, int]:
    return {'numerator': value.numerator, 'denominator': value.denominator}


def fraction_from_payload(value: object) -> Fraction:
    if not isinstance(value, Mapping) or set(value) != {'numerator', 'denominator'}:
        raise ValueError('a rational body requires numerator and denominator')
    numerator = value['numerator']
    denominator = value['denominator']
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('a rational body requires integers and a positive denominator')
    return Fraction(numerator, denominator)


def parse_probability(value: object) -> Fraction:
    if isinstance(value, Mapping):
        probability = fraction_from_payload(value)
    elif type(value) is int or isinstance(value, (str, Fraction)):
        try:
            probability = Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError('invalid rational probability') from exc
    else:
        raise ValueError('probability must have an exact rational representation')
    if not 0 <= probability <= 1:
        raise ValueError('probability must be between 0 and 1 inclusive')
    return probability
