import pytest
from journey_api.errors import ApiError
from journey_api.feishu_directory import FeishuDirectory


def user(uid,name='同名',**status):
    return {'open_id':uid,'name':name,'department_ids':['od-team'], 'status':{'is_activated':True,**status},'avatar':{'avatar_72':'https://s1-imfile.feishucdn.com/avatar'}}


def test_scoped_pagination_deduplicates_users_and_filters_inactive(monkeypatch):
    d=FeishuDirectory(None);calls=[]
    def data(path,params=None):
        calls.append((path,params))
        if path.endswith('/scopes'):return {'department_ids':['0'],'has_more':False}
        if path.endswith('/0/children'):return {'items':[{'open_department_id':'od-team','name':'产品部'}]}
        if path.endswith('/children'):return {'items':[]}
        if path.endswith('/find_by_department'):
            if params['department_id']=='0':return {'items':[user('ou_same')],'has_more':False}
            if params.get('page_token'):return {'items':[user('ou_second'),user('ou_left',is_resigned=True)]}
            return {'items':[user('ou_same'),user('ou_frozen',is_frozen=True)],'has_more':True,'page_token':'next'}
        raise AssertionError(path)
    monkeypatch.setattr(d,'_data',data)
    matches=d.search('同名')['items']
    assert [m['open_id'] for m in matches]==['ou_same','ou_second']
    assert matches[0]['departments']==['产品部']
    count=len(calls);d.search('同名');assert len(calls)==count


def test_grant_lookup_ignores_search_cache_and_rechecks_employment(monkeypatch):
    d=FeishuDirectory(None);d._profiles=[{'open_id':'ou_one','name':'缓存名字'}]
    monkeypatch.setattr(d,'_data',lambda *args:{'user':user('ou_one',is_resigned=True)})
    with pytest.raises(ApiError):d.get_user('ou_one')
    monkeypatch.setattr(d,'_data',lambda *args:{'user':user('ou_different')})
    with pytest.raises(ApiError):d.get_user('ou_one')


def test_missing_field_permissions_are_not_misreported_as_empty_directory():
    with pytest.raises(ApiError) as error:FeishuDirectory._active({'open_id':'ou_a'})
    assert error.value.code=='DIRECTORY_PERMISSION_REQUIRED'


def test_repeating_page_token_fails_without_partial_results(monkeypatch):
    d=FeishuDirectory(None)
    monkeypatch.setattr(d,'_data',lambda *args:{'has_more':True,'page_token':'same'})
    with pytest.raises(ApiError):list(d._pages('/contact/v3/scopes',{}))


def test_all_member_scope_with_groups_reads_root_users_and_descendants(monkeypatch):
    d=FeishuDirectory(None);calls=[]
    def data(path,params=None):
        calls.append((path,params))
        if path.endswith('/scopes'):return {'department_ids':['od-team'],'group_ids':['g-all'],'user_ids':['ou_team']}
        if path.endswith('/0/children'):return {'items':[{'open_department_id':'od-team','name':'产品部'}]}
        if path.endswith('/children'):return {'items':[]}
        if path.endswith('/find_by_department'):
            if params['department_id']=='0':
                if params.get('page_token'):return {'items':[user('ou_root2')]}
                return {'items':[user('ou_root')],'has_more':True,'page_token':'next'}
            return {'items':[user('ou_team'),user('ou_root'),user('ou_left',is_resigned=True)]}
        raise AssertionError(path)
    monkeypatch.setattr(d,'_data',data)
    matches=d.search('同名')['items']
    assert {m['open_id'] for m in matches}=={'ou_root','ou_root2','ou_team'}
    assert all(m['departments']==['产品部'] for m in matches)
    assert len([p for path,p in calls if path.endswith('/find_by_department') and p['department_id']=='0'])==2


def test_group_scope_without_all_member_access_cannot_return_partial_results(monkeypatch):
    d=FeishuDirectory(None)
    def data(path,params=None):
        if path.endswith('/scopes'):return {'department_ids':['od-team'],'group_ids':['g-only']}
        assert params['department_id']=='0'
        raise ApiError(503,'DIRECTORY_UNAVAILABLE','No root access')
    monkeypatch.setattr(d,'_data',data)
    with pytest.raises(ApiError):d.search('同名')
    assert d._profiles is None


def fake_transport(monkeypatch, responses):
    import io,json
    from urllib import request
    from journey_api import feishu_directory
    calls=[]
    def open_response(self,req,timeout):
        calls.append(req)
        item=responses.pop(0)
        if isinstance(item,Exception):raise item
        status,payload=item
        response=io.BytesIO(json.dumps(payload).encode())
        response.status=status
        return response
    monkeypatch.setattr(request.OpenerDirector,'open',open_response)
    monkeypatch.setattr(feishu_directory.time,'sleep',lambda _:None)
    return calls


@pytest.mark.parametrize('code',[99991663,99991665])
def test_invalid_cached_tenant_token_refreshes_once(monkeypatch,code):
    import time
    from types import SimpleNamespace
    d=FeishuDirectory(SimpleNamespace(feishu_app_id='test-app',feishu_app_secret='test-secret'))
    d._token='old-token';d._token_until=time.monotonic()+3600
    calls=fake_transport(monkeypatch,[(401,{'code':code}),
        (200,{'code':0,'tenant_access_token':'new-token','expire':7200}),
        (200,{'code':0,'data':{'items':[]}})])
    assert d._data('/contact/v3/departments/0/children')=={'items':[]}
    assert len(calls)==3 and calls[-1].headers['Authorization']=='Bearer new-token'


def test_repeated_invalid_token_stops_and_never_returns_partial_data(monkeypatch):
    import time
    from types import SimpleNamespace
    d=FeishuDirectory(SimpleNamespace(feishu_app_id='test-app',feishu_app_secret='test-secret'))
    d._token='old-token';d._token_until=time.monotonic()+3600
    calls=fake_transport(monkeypatch,[(400,{'code':99991663}),
        (200,{'code':0,'tenant_access_token':'new-token','expire':7200}),
        (400,{'code':99991663})])
    with pytest.raises(ApiError) as exc:d._data('/contact/v3/departments/0/children')
    assert exc.value.code=='DIRECTORY_TOKEN_INVALID' and len(calls)==3


@pytest.mark.parametrize('first',[(429,{}),(503,{}),(400,{'code':99991400}),TimeoutError()])
def test_transient_read_failures_retry_once(monkeypatch,first):
    calls=fake_transport(monkeypatch,[first,(200,{'code':0,'data':{'items':[]}})])
    assert FeishuDirectory(None)._call('/contact/v3/departments/0/children',token='test')['code']==0
    assert len(calls)==2


def test_permission_and_other_business_errors_are_distinguished_and_safely_logged(monkeypatch,caplog):
    calls=fake_transport(monkeypatch,[(403,{'code':99991672,'msg':'secret-provider-data'}),
                                    (400,{'code':123456,'msg':'secret-provider-data'})])
    with pytest.raises(ApiError) as exc:FeishuDirectory(None)._call('/contact/v3/departments/0/children',token='private-token')
    assert exc.value.code=='DIRECTORY_PERMISSION_REQUIRED' and len(calls)==1
    with pytest.raises(ApiError) as exc:FeishuDirectory(None)._call('/contact/v3/departments/0/children',token='private-token')
    assert exc.value.details['provider_code']==123456
    assert '权限' not in exc.value.message and '123456' in exc.value.message
    assert 'secret-provider-data' not in caplog.text and 'private-token' not in caplog.text


def test_root_department_picker_does_not_traverse_children(monkeypatch):
    from journey_api.department_directory import DepartmentDirectory
    d=FeishuDirectory(None);calls=[]
    def pages(path,params):
        calls.append(path)
        assert path.endswith('/0/children')
        yield {'items':[{'open_department_id':'a','name':'总经办'}]}
        yield {'items':[{'open_department_id':'b','name':'财务法务合规部'}]}
    monkeypatch.setattr(d,'_pages',pages)
    assert len(DepartmentDirectory(d).departments(root_only=True))==2
    assert len(calls)==1


def test_explicit_user_scope_is_still_read_without_all_member_access(monkeypatch):
    d=FeishuDirectory(None)
    def data(path,params=None):
        if path.endswith('/scopes'):return {'user_ids':['ou_direct']}
        assert path.endswith('/users/ou_direct')
        return {'user':user('ou_direct')}
    monkeypatch.setattr(d,'_data',data)
    assert d.read_profiles()[0]['open_id']=='ou_direct'


def test_snapshot_rejects_missing_or_unknown_department_membership(monkeypatch):
    from journey_api.department_directory import DepartmentDirectory
    d=FeishuDirectory(None)
    monkeypatch.setattr(DepartmentDirectory,'departments',lambda _: [
        {'id':'od-team','name':'开发部','parent_id':'0','path_ids':['od-team']}])
    monkeypatch.setattr(d,'read_profiles',lambda: [{'department_ids':None}])
    with pytest.raises(ApiError) as exc:d.read_snapshot()
    assert exc.value.code=='DIRECTORY_PERMISSION_REQUIRED'
    monkeypatch.setattr(d,'read_profiles',lambda: [{'department_ids':['od-unknown']}])
    with pytest.raises(ApiError) as exc:d.read_snapshot()
    assert exc.value.code=='DIRECTORY_INCOMPLETE'


def test_employee_number_is_taken_from_provider_not_account_id():
    person=user('ou_not_a_number');person.update(employee_no='MCE0000004',job_title='项目经理')
    profile=FeishuDirectory._profile(person,{'od-team':'开发部'})
    assert profile['employee_no']=='MCE0000004'
    assert profile['job_title']=='项目经理'
    assert FeishuDirectory._profile(user('ou_not_a_number'),{})['employee_no']==''


def test_snapshot_builds_full_department_path_without_extra_member_requests(monkeypatch):
    from journey_api.department_directory import DepartmentDirectory
    d=FeishuDirectory(None)
    person=FeishuDirectory._profile(user('ou_person'),{'od-team':'开发部'})
    monkeypatch.setattr(d,'read_profiles',lambda:[person])
    tree=[{'id':'od-center','name':'AI平台与数据治理中心','parent_id':'0','path_ids':['od-center']},
          {'id':'od-team','name':'开发部','parent_id':'od-center','path_ids':['od-center','od-team']}]
    monkeypatch.setattr(DepartmentDirectory,'departments',lambda self:tree)
    profiles,_=d.read_snapshot()
    assert profiles[0]['department_paths']==['AI平台与数据治理中心 / 开发部']
    assert profiles[0]['departments']==['开发部']
