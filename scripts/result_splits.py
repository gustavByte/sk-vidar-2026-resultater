"""Preserve official split evidence across collection and narrow publication."""
from decimal import Decimal, InvalidOperation
import math
import re

SPLIT_FIELDS = ('split_first_label', 'split_first_display', 'split_second_label',
                'split_second_display', 'split_delta_display', 'split_state')


def seconds(value):
    if value is None or value == '':
        return None
    try:
        parts = str(value).strip().replace(',', '.').split(':')
        if not 1 <= len(parts) <= 3 or any(not re.fullmatch(r'\d+(?:\.\d+)?', p) for p in parts):
            return None
        nums = [Decimal(p) for p in parts]
        if any(v >= 60 for v in nums[1:]):
            return None
        result = sum(v * (60 ** i) for i, v in enumerate(reversed(nums)))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def duration(value):
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise ValueError('Ugyldig splittid')
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    sec = value % 60
    text = format(sec, 'f').rstrip('0').rstrip('.') if sec % 1 else str(int(sec))
    if sec < 10:
        text = '0' + text
    return f'{hours}:{minutes:02}:{text}' if hours else f'{minutes}:{text}'


def split_spec(distance):
    key = re.sub(r'\s+', '', str(distance).casefold()).replace(',', '.')
    return {
        'maraton': (42.195, 21.0975, 'Første halvmaraton', 'Siste halvmaraton'),
        'marathon': (42.195, 21.0975, 'Første halvmaraton', 'Siste halvmaraton'),
        '42.195km': (42.195, 21.0975, 'Første halvmaraton', 'Siste halvmaraton'),
        'halvmaraton': (21.0975, 10.0, 'Første 10 km', 'Siste 11,0975 km'),
        'halfmarathon': (21.0975, 10.0, 'Første 10 km', 'Siste 11,0975 km'),
        '21.0975km': (21.0975, 10.0, 'Første 10 km', 'Siste 11,0975 km'),
        '10km': (10.0, 5.0, 'Første 5 km', 'Siste 5 km'),
        '5km': (5.0, 2.5, 'Første 2,5 km', 'Siste 2,5 km'),
    }.get(key)


def ultimate_split_evidence(raw, source, candidate):
    """Read cumulative timing cells, never photo captions or segment totals."""
    from bs4 import BeautifulSoup
    spec = split_spec(candidate.get('distance'))
    if not spec:
        return None
    soup = BeautifulSoup(raw.decode('utf-8-sig'), 'html.parser')
    points = {}
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) != 12 or 'details_racetime' not in cells[1].get('class', []):
            continue
        label = cells[0].get_text(' ', strip=True)
        if label in points:
            raise ValueError('Flere mellomtider med samme navn')
        points[label] = cells[1].get_text(' ', strip=True)
    total_km, checkpoint_km, first_label, second_label = spec
    half_labels = {'half', 'split half', 'half marathon', 'halfmarathon', 'halvmaraton'}
    def distance_at(label):
        text = label.casefold().strip()
        if text in half_labels:
            return total_km / 2
        match = re.fullmatch(r'(?:split\s+)?(\d+(?:[.,]\d+)?)\s*(?:km|k)', text)
        return float(match[1].replace(',', '.')) if match else None
    halfway = [(label, value) for label, value in points.items()
               if distance_at(label) is not None and math.isclose(distance_at(label), total_km / 2, abs_tol=0.00001)]
    if total_km == 21.0975 and halfway:
        checkpoint_km = total_km / 2
        first_label, second_label = 'Første halvdel', 'Siste halvdel'
    checkpoints = [(label, value) for label, value in points.items()
                   if distance_at(label) is not None and math.isclose(distance_at(label), checkpoint_km, abs_tol=0.00001)]
    finish = [value for label, value in points.items() if label.casefold() in {'finish', 'mål', 'mal'}
              or (distance_at(label) is not None and math.isclose(distance_at(label), total_km, abs_tol=0.00001))]
    evidence = {'status':'unavailable','source':source,'distance_km':total_km,'checkpoint_km':checkpoint_km,
                'first_label':first_label,'second_label':second_label,'timing_points':points}
    if not checkpoints:
        evidence['reason']='Offisiell detaljvisning mangler den aktuelle mellompasseringen.'
        return evidence
    if len(checkpoints) != 1 or len(finish) != 1:
        raise ValueError('Mangler entydig mellomtid eller sluttid')
    reported, chip = seconds(candidate.get('reported_time')), seconds(candidate.get('chip_time'))
    net = re.search(r'\bnet time\s+([\d:.,]+)', soup.get_text(' ', strip=True), re.I)
    if net and seconds(net[1]) is not None:
        if chip is not None and chip != seconds(net[1]):
            raise ValueError('Nettotiden er endret mellom kildene')
        chip = seconds(net[1])
    finish_value = seconds(finish[0])
    if finish_value is None:
        raise ValueError('Ugyldig sluttid i mellomtidstabellen')
    basis = 'reported' if finish_value == reported else 'chip' if finish_value == chip else ''
    if not basis:
        raise ValueError('Mellomtidstabellens sluttid avviker fra resultatet')
    evidence.update(status='available', cumulative_time=checkpoints[0][1], cumulative_basis=basis,
                    finish_time=finish[0], reported_time=candidate.get('reported_time'),
                    chip_time=duration(chip) if chip is not None else '')
    return evidence


def split_fields(candidate, time_basis):
    """Convert a documented cumulative split to the selected finish-time basis."""
    evidence = candidate.get('split_evidence')
    if not evidence or evidence.get('status') == 'unavailable':
        return {}
    if evidence.get('status') != 'available':
        raise ValueError('Mellomtidene må kontrolleres før publisering')
    if time_basis not in {'reported','chip'}:
        raise ValueError('Mellomtidene mangler valgt tidsgrunnlag')
    total = seconds(candidate.get(time_basis+'_time'))
    first = seconds(evidence.get('cumulative_time'))
    source_finish = seconds(evidence.get('finish_time'))
    source_basis = evidence.get('cumulative_basis')
    if source_basis not in {'reported','chip'} or None in (total, first, source_finish):
        raise ValueError('Ufullstendig kilde for mellomtider')
    if source_finish != seconds(evidence.get(source_basis+'_time')):
        raise ValueError('Mellomtidens tidsgrunnlag er inkonsistent')
    if total != seconds(evidence.get(time_basis+'_time')):
        raise ValueError('Sluttiden avviker fra splittkilden')
    # Shift the cumulative clock by the documented difference between finishes.
    # This handles both gross->chip and chip->gross, without using time-of-day.
    first += total - source_finish
    second = total - first
    if first <= 0 or second <= 0:
        raise ValueError('Mellomtiden må ligge mellom start og mål')
    equal = math.isclose(2*float(evidence['checkpoint_km']),float(evidence['distance_km']),abs_tol=0.00001)
    delta = second-first
    return {'split_first_label':evidence['first_label'],'split_second_label':evidence['second_label'],
            'split_first_display':duration(first),'split_second_display':duration(second),
            'split_delta_display':(('+' if delta>0 else '−' if delta<0 else '')+duration(abs(delta))) if equal else '',
            'split_state':('slow' if delta>0 else 'fast' if delta<0 else 'even') if equal else ''}


def apply_split_fields(result, fields):
    present = {k:fields[k] for k in SPLIT_FIELDS if k in fields}
    if not present or not any(present.values()):
        return
    if set(present) != set(SPLIT_FIELDS):
        raise ValueError('Ufullstendige publiseringsfelt for splitter')
    first, second = seconds(present['split_first_display']), seconds(present['split_second_display'])
    if first is None or second is None or first<=0 or second<=0 or first+second != seconds(result['result_time_seconds']):
        raise ValueError('Splitter summerer ikke til den publiserte sluttiden')
    result.update(present)


def split_source_text(rows):
    lines=[]
    for row in rows:
        if row.get('split_first_display'):
            lines.append(f"- {row['athlete_name']} | {row['split_first_label']}: {row['split_first_display']} | {row['split_second_label']}: {row['split_second_display']} | Splitt: {row['split_delta_display'] or 'ulike deldistanser'}")
    return ('\nMellomtider:\nSamme tidsgrunnlag som sluttiden. Siste del = sluttid minus første del. Ved omregning fra brutto til netto brukes dokumentert startforsinkelse; avrundede kildetider kan gi ett sekund avvik.\n'+'\n'.join(lines)+'\n') if lines else ''
