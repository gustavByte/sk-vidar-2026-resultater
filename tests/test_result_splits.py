from pathlib import Path
import copy
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from result_splits import SPLIT_FIELDS, ultimate_split_evidence, split_fields, apply_split_fields, seconds, split_source_text


def evidence(first='1:14:52', finish='2:28:26', chip='2:27:49', distance=42.195, checkpoint=21.0975):
    return {'status':'available','cumulative_time':first,'finish_time':finish,'reported_time':finish,
            'chip_time':chip,'cumulative_basis':'reported','checkpoint_km':checkpoint,'distance_km':distance,
            'first_label':'Første halvmaraton','second_label':'Siste halvmaraton'}


def runner():
    return {'reported_time':'2:28:26','chip_time':'2:27:49','split_evidence':evidence()}


def test_amsterdam_net_splits_exclude_start_delay_and_sum_to_selected_finish():
    fields=split_fields(runner(),'chip')
    assert fields['split_first_display']=='1:14:15'
    assert fields['split_second_display']=='1:13:34'
    assert fields['split_delta_display']=='−0:41'
    assert fields['split_state']=='fast'
    result={'result_time_seconds':8869.0}
    apply_split_fields(result,fields)
    assert seconds(result['split_first_display'])+seconds(result['split_second_display'])==8869
    gross=split_fields(runner(),'reported')
    assert gross['split_first_display']=='1:14:52'
    assert gross['split_second_display']==fields['split_second_display']


def test_hytteplan_net_and_reported_basis_already_agree():
    c={'reported_time':'30:50','chip_time':'30:50','split_evidence':evidence('15:18','30:50','30:50',10,5)}
    f=split_fields(c,'chip')
    assert (f['split_first_display'],f['split_second_display'],f['split_delta_display'])==('15:18','15:32','+0:14')


def test_unequal_half_marathon_parts_are_not_labeled_positive_or_negative_split():
    c={'reported_time':'1:30:00','chip_time':'1:30:00','split_evidence':evidence('40:00','1:30:00','1:30:00',21.0975,10)}
    f=split_fields(c,'reported')
    assert f['split_second_display']=='50:00'
    assert f['split_state']==f['split_delta_display']==''


@pytest.mark.parametrize('field,value',[('chip_time','2:27:48'),('cumulative_time','0:10'),('cumulative_basis','unknown')])
def test_inconsistent_or_impossible_sources_block_splits(field,value):
    c=runner();c['split_evidence'][field]=value
    with pytest.raises(ValueError):split_fields(c,'chip')


def test_missing_checkpoint_stays_blank_without_interpolation():
    c=runner();c['split_evidence']={'status':'unavailable','reason':'No timing mat'}
    assert split_fields(c,'chip')=={}
    apply_split_fields({'result_time_seconds':8869},dict.fromkeys(SPLIT_FIELDS,''))
    with pytest.raises(ValueError):apply_split_fields({'result_time_seconds':8869},{'split_first_label':'Half'})


def table_row(label,cumulative,segment='1:00',clock='10:00:00'):
    return '<tr><td>'+label+'</td><td class="details_racetime">'+cumulative+'</td>'+''.join('<td>'+v+'</td>' for v in ['speed','1','1','1',segment,'speed','1','1','1',clock])+'</tr>'


def test_ultimate_uses_cumulative_cells_not_segments_photos_or_clock():
    raw=('<p>net time 02:27:49 gross time 02:28:26</p><table>'+table_row('Split Half','1:14:52','4:00','10:14:51')+table_row('Finish','2:28:26','7:39','11:28:26')+'<tr><td>Split Half</td><td>photo</td></tr></table>').encode()
    c={'distance':'Maraton','reported_time':'2:28:26','chip_time':'2:27:49'}
    e=ultimate_split_evidence(raw,{'sha256':'a'*64,'url':'https://example.org/detail'},c)
    assert e['status']=='available' and e['cumulative_time']=='1:14:52'
    assert split_fields(dict(c,split_evidence=e),'chip')['split_first_display']=='1:14:15'
    missing=raw.replace(b'Split Half',b'Split 20 KM')
    assert ultimate_split_evidence(missing,{},c)['status']=='unavailable'


def test_public_source_keeps_splits_without_private_evidence():
    row=dict(athlete_name='Test Runner',**split_fields(runner(),'chip'),warnings=['private membership'])
    text=split_source_text([row])
    assert '1:14:15' in text and '1:13:34' in text and 'startforsinkelse' in text
    assert 'private' not in text
