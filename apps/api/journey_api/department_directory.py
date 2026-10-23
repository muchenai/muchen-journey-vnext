"""Read-only department traversal and explicit job-title matching."""
from urllib.parse import quote
from journey_api.errors import ApiError

ALL_DEPARTMENTS = {'总经办', 'PMO经营治理办公室', '客户增长与战略解决方案部', '财务法务合规部'}
TITLE_DEPARTMENTS = {'AI平台与数据治理中心', '人才与专家网络中心', '行政与职场运营部', 'AI数据交付中心', '品牌策划与内容传播部'}


def normalized(value):
    return ''.join(value.split())


class DepartmentDirectory:
    def __init__(self, directory):
        self.directory = directory

    def preview_snapshot(self, *, include_people=True):
        return self.directory.bulk_snapshot(include_people=include_people)

    def departments(self, *, root_only=False):
        result, pending, visited = [], [('0', [])], set()
        while pending:
            parent, path = pending.pop(0)
            if parent in visited:
                continue
            visited.add(parent)
            if len(visited) > 1000:
                raise ApiError(503, 'DIRECTORY_INCOMPLETE', '部门数量超出同步范围，未返回不完整名单。')
            for page in self.directory._pages('/contact/v3/departments/' + quote(parent, safe='') + '/children', {
                'department_id_type': 'open_department_id', 'fetch_child': 'false', 'page_size': 50,
            }):
                for child in page.get('items', []):
                    department_id, name = child['open_department_id'], child['name']
                    child_path = path + [department_id]
                    if any(item['id'] == department_id for item in result):
                        continue
                    default = 'all' if not path and normalized(name) in ALL_DEPARTMENTS else 'title' if not path and normalized(name) in TITLE_DEPARTMENTS else 'off'
                    result.append({'id': department_id, 'name': name, 'parent_id': parent, 'path_ids': child_path, 'default_mode': default})
                    if not root_only:
                        pending.append((department_id, child_path))
        return result

    @staticmethod
    def expanded(tree, rules):
        by_id = {d['id']: d for d in tree}
        if any(r['department_id'] not in by_id for r in rules):
            raise ApiError(409, 'DEPARTMENT_CHANGED', '所选部门已变化或不可见，请重新加载部门。')
        return {d['id']: 'all' if any(r['mode'] == 'all' for r in rules if r['department_id'] in d['path_ids']) else 'title'
                for d in tree if any(r['department_id'] in d['path_ids'] for r in rules)}

    @staticmethod
    def profile(user, tree):
        if not user.get('open_id') or 'department_ids' not in user:
            raise ApiError(503, 'DIRECTORY_PERMISSION_REQUIRED', '缺少员工部门信息，请检查通讯录权限。')
        names = {d['id']: d['name'] for d in tree}
        return {'open_id': user['open_id'], 'name': user['name'], 'job_title': user.get('job_title') or '',
                'department_ids': sorted(set(user['department_ids'])),
                'departments': [names.get(d, '其他部门') for d in user['department_ids']]}

    @staticmethod
    def match(profile, expanded):
        modes = {expanded[d] for d in profile['department_ids'] if d in expanded}
        if 'all' in modes:
            return 'all'
        if 'title' in modes and any(word in profile['job_title'] for word in ('经理', '助理')):
            return 'title'
        return None

    def candidates(self, tree, rules):
        expanded = self.expanded(tree, rules)
        people = {}
        for department_id in expanded:
            for page in self.directory._pages('/contact/v3/users/find_by_department', {
                'department_id': department_id, 'department_id_type': 'open_department_id',
                'user_id_type': 'open_id', 'page_size': 50,
            }):
                for user in page.get('items', []):
                    if self.directory._active(user):
                        profile = self.profile(user, tree)
                        people[profile['open_id']] = profile
                    if len(people) > 5000:
                        raise ApiError(503, 'DIRECTORY_INCOMPLETE', '人员过多，请缩小部门范围后预览。')
        return list(people.values())

    def fresh(self, open_id, tree):
        user = self.directory._data('/contact/v3/users/' + quote(open_id, safe=''), {
            'user_id_type': 'open_id', 'department_id_type': 'open_department_id',
        }).get('user', {})
        if user.get('open_id') != open_id or not self.directory._active(user):
            raise ApiError(422, 'DIRECTORY_MEMBER_INVALID', '该成员已不属于可授权的在职员工。')
        return self.profile(user, tree)
