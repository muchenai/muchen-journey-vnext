"""Publication boundaries, real files and per-learner favorites in an isolated DB."""
import base64
import uuid
from test_novice_tasks import setup
from test_community_modules import change, command, snapshot
from test_reviewer_workbench import create_submission
from test_wp09_feishu_identity import assert_ok


def listing(learner, module):
    return assert_ok(learner[0].get('/api/v1/me/knowledge/' + module))


def test_explicit_modules_publication_updates_and_existing_categories(setup):
    staff, learner, *_ = setup
    cat = change(staff, 'knowledge', 'saveCategory', {'name':'知识分类'+uuid.uuid4().hex[:5]})['result']
    item = change(staff, 'knowledge', 'saveLink', dict(title='跨模块资料', url='https://example.com/manual',
        categoryId=cat['id'], modules=['dashboard','village'], status='published'))['result']
    for module in ['dashboard','village','academy','guild']:
        data = listing(learner, module)
        assert any(c['id']==cat['id'] for c in data['categories'])
        assert any(r['id']==item['id'] for r in data['items']) == (module in item['modules'])
    edited = change(staff, 'knowledge', 'updateItem', {**item, 'title':'更新标题', 'modules':['academy']})['result']
    assert not any(r['id']==item['id'] for r in listing(learner,'village')['items'])
    assert next(r for r in listing(learner,'academy')['items'] if r['id']==item['id'])['title']=='更新标题'
    change(staff,'knowledge','removeCategory',{'id':cat['id']})
    assert next(r for r in listing(learner,'academy')['items'] if r['id']==item['id'])['categoryId']=='uncategorized'
    change(staff,'knowledge','setItemStatus',{'id':edited['id'],'status':'unpublished'})
    assert not any(r['id']==item['id'] for r in listing(learner,'academy')['items'])


def test_files_and_favorites_require_current_publication_and_learner(setup):
    staff, learner, *_ = setup
    content=b'%PDF-1.7\nlocal knowledge file'
    file=assert_ok(command(staff,'knowledge','beginUpload',dict(fileName='资料.pdf',size=len(content))))['result']
    assert_ok(command(staff,'knowledge','uploadChunk',dict(id=file['id'],position=0,data=base64.b64encode(content).decode())))
    item=change(staff,'knowledge','completeUpload',dict(id=file['id'],categoryId='company',modules=['village','guild'],status='published'))['result']
    path=f'/api/v1/me/knowledge/village/files/{item["id"]}/chunks/0'
    assert base64.b64decode(assert_ok(learner[0].get(path))['data'])==content
    assert learner[0].get(path.replace('/village/','/academy/')).status_code==404
    assert staff[0].get(path).status_code in (401,403)
    assert learner[0].get(path[:-1]+'999').status_code==404
    favorite=f'/api/v1/me/knowledge/village/favorites/{item["id"]}'
    args=dict(headers={'X-CSRF-Token':learner[1]},json={'saved':True})
    assert_ok(learner[0].post(favorite,**args)); assert_ok(learner[0].post(favorite,**args))
    assert next(r for r in listing(learner,'guild')['items'] if r['id']==item['id'])['saved'] is True
    flow=create_submission('knowledge-favorite-'+uuid.uuid4().hex)
    other=(flow['learner'],flow['csrf'])
    assert next(r for r in listing(other,'guild')['items'] if r['id']==item['id'])['saved'] is False
    assert learner[0].post(favorite,json={'saved':False}).status_code==403
    change(staff,'knowledge','setItemStatus',{'id':item['id'],'status':'unpublished'})
    assert learner[0].get(path).status_code==404
    assert learner[0].post(favorite,**args).status_code==404
    change(staff,'knowledge','setItemStatus',{'id':item['id'],'status':'published'})
    assert next(r for r in listing(learner,'village')['items'] if r['id']==item['id'])['saved'] is True
    change(staff,'knowledge','removeItem',{'id':item['id']})
    assert learner[0].get(path).status_code==404


def test_no_inferred_module_or_automatic_legacy_publication(setup):
    staff, learner, *_ = setup
    item=change(staff,'knowledge','saveLink',dict(title='未设范围资料',url='https://example.com',categoryId='company'))['result']
    assert item['modules']==[] and item['status']=='draft'
    for module in ['dashboard','village','academy','guild']:
        assert not any(r['id']==item['id'] for r in listing(learner,module)['items'])
    for modules in [[],['unknown'],['all'],'village',[{}]]:
        payload=dict(title='无效范围',url='https://example.com',modules=modules,status='published')
        assert command(staff,'knowledge','saveLink',payload,snapshot(staff,'knowledge')['revision']).status_code==422
    assert learner[0].get('/api/v1/me/knowledge/unknown').status_code==422
