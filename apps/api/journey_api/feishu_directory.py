"""Company directory through the same tenant application used by OAuth.

Only minimal profiles are returned. App tokens never leave this process.
"""
import json
import logging
import time
from functools import lru_cache
from threading import RLock
from urllib import error, parse, request

from journey_api.config import get_settings
from journey_api.errors import ApiError

logger = logging.getLogger(__name__)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class FeishuDirectory:
    def __init__(self, settings):
        self.settings = settings
        self._token = ""
        self._token_until = 0
        self._profiles = None
        self._profiles_until = 0
        self._lock = RLock()

    def _call(self, path, params=None, *, body=None, token=None):
        url = "https://open.feishu.cn/open-apis" + path
        if params:
            url += "?" + parse.urlencode(params)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = request.Request(url, data=json.dumps(body).encode() if body else None, headers=headers)
        for attempt in range(2):
            try:
                try:
                    response = request.build_opener(NoRedirect()).open(req, timeout=8)
                except error.HTTPError as exc:
                    response = exc
                with response:
                    status = response.status
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError()
                if status == 429 or status >= 500:
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    raise ApiError(503, 'DIRECTORY_BUSY', '飞书通讯录服务繁忙，请稍后重新读取。',
                                   details={'http_status': status}, retryable=True)
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError()
                code = value.get('code')
                if code == 0 and status < 400:
                    return value
                safe_code = code if isinstance(code, int) else None
                # Never log provider messages, credentials, URLs or personnel data.
                logger.warning(json.dumps({'event': 'directory.provider_error', 'provider_code': safe_code,
                                           'http_status': status, 'endpoint': 'token' if body else 'directory'}))
                details = {'provider_code': safe_code, 'http_status': status}
                if code in (99991672, 99991676):
                    raise ApiError(503, 'DIRECTORY_PERMISSION_REQUIRED', '飞书返回通讯录权限不足，请检查应用身份权限及可见范围。', details=details)
                if token and code in (99991663, 99991665):
                    raise ApiError(503, 'DIRECTORY_TOKEN_INVALID', '通讯录访问凭证暂时失效，请重新读取。', details=details, retryable=True)
                if code == 99991400:
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    raise ApiError(503, 'DIRECTORY_BUSY', '飞书通讯录请求过于频繁，请稍后重新读取。', details=details, retryable=True)
                suffix = f'（错误码 {safe_code}）' if safe_code is not None else ''
                raise ApiError(503, 'DIRECTORY_UNAVAILABLE', '飞书通讯录读取失败' + suffix + '，请重试；持续失败请联系维护人员。', details=details)
            except (error.URLError, TimeoutError, ValueError, TypeError) as exc:
                if attempt == 0:
                    time.sleep(.3)
                    continue
                logger.warning(json.dumps({'event': 'directory.transport_error', 'error_type': type(exc).__name__}))
                raise ApiError(503, 'DIRECTORY_UNAVAILABLE', '连接飞书通讯录失败，请稍后重新读取。', retryable=True) from exc

    def _tenant_token(self):
        with self._lock:
            if time.monotonic() >= self._token_until:
                result = self._call("/auth/v3/tenant_access_token/internal", body={
                    "app_id": self.settings.feishu_app_id, "app_secret": self.settings.feishu_app_secret})
                self._token = result.get("tenant_access_token", "")
                if not self._token:
                    raise ApiError(503, "DIRECTORY_UNAVAILABLE", "无法获取公司通讯录访问凭证。")
                self._token_until = time.monotonic() + max(0, min(int(result.get("expire", 0))-60, 3600))
            return self._token

    def _data(self, path, params=None):
        token = self._tenant_token()
        try:
            return self._call(path, params, token=token).get('data', {})
        except ApiError as exc:
            if exc.code != 'DIRECTORY_TOKEN_INVALID':
                raise
            with self._lock:
                if self._token == token:
                    self._token_until = 0
            # Exactly one refresh; a second rejection propagates instead of looping.
            return self._call(path, params, token=self._tenant_token()).get('data', {})

    def _pages(self, path, params):
        params = dict(params)
        seen = set()
        for _ in range(200):
            data = self._data(path, params)
            yield data
            if not data.get("has_more"):
                return
            token = data.get("page_token")
            if not token or token in seen:
                break
            seen.add(token)
            params["page_token"] = token
        raise ApiError(503, "DIRECTORY_INCOMPLETE", "通讯录同步未完成，请稍后重试；未显示不完整的搜索结果。")

    @staticmethod
    def _active(user):
        if "name" not in user or "status" not in user:
            raise ApiError(503, "DIRECTORY_PERMISSION_REQUIRED", "缺少成员姓名或在职状态字段，请开通获取用户基本信息、获取用户受雇信息权限并发布。")
        status = user.get("status") or {}
        return (status.get("is_activated") is True
                and not any(status.get(key) for key in ("is_frozen", "is_resigned", "is_exited", "is_unjoin"))
                and not user.get("is_frozen"))

    @staticmethod
    def _profile(user, departments):
        avatar = (user.get("avatar") or {}).get("avatar_72", "")
        return {"open_id": user["open_id"], "name": user["name"],
                "avatar": avatar if avatar.startswith("https://") else "",
                "job_title": user.get("job_title") or "",
                "employee_no": user.get("employee_no") or "",
                "department_ids": sorted(set(user['department_ids'])) if 'department_ids' in user else None,
                "departments": [departments.get(d, "公司成员") for d in user.get("department_ids", [])]}

    def get_user(self, open_id):
        # Fresh provider lookup on every grant/reactivation; never trust a name,
        # caller-provided profile or the cached search result for authorization.
        data = self._data("/contact/v3/users/" + parse.quote(open_id, safe=""),
                          {"user_id_type": "open_id", "department_id_type": "open_department_id"})
        user = data.get("user", {})
        if user.get("open_id") != open_id or not user.get("name") or not self._active(user):
            raise ApiError(422, "DIRECTORY_MEMBER_INVALID", "该账号不是当前可授权的在职公司成员，请重新搜索选择。")
        return self._profile(user, {})

    def read_profiles(self):
        users, roots, departments = {}, set(), {}
        has_groups = False
        direct_users = set()
        for page in self._pages("/contact/v3/scopes", {"user_id_type": "open_id", "department_id_type": "open_department_id", "page_size": 100}):
            roots.update(page.get("department_ids", []))
            direct_users.update(page.get("user_ids", []))
            has_groups = has_groups or bool(page.get("group_ids"))
        if has_groups:
            # All-member scopes also include every group. Feishu only
            # permits a root-user query with all-member access; require
            # that proof before traversing the full department tree.
            # A restricted group-only scope must still fail closed.
            for page in self._pages("/contact/v3/users/find_by_department", {
                    "department_id": "0", "department_id_type": "open_department_id",
                    "user_id_type": "open_id", "page_size": 50}):
                for user in page.get("items", []):
                    if self._active(user) and user.get("open_id"):
                        users[user["open_id"]] = user
            roots = {"0"}
        if not has_groups:
            for uid in sorted(direct_users):
                user = self._data("/contact/v3/users/" + parse.quote(uid, safe=""),
                    {"user_id_type": "open_id", "department_id_type": "open_department_id"}).get("user", {})
                if self._active(user) and user.get("open_id"):
                    users[user["open_id"]] = user
        pending = list(roots)
        visited = set()
        while pending:
            department = pending.pop()
            if department in visited:
                continue
            visited.add(department)
            if department != "0" and department not in departments:
                info = self._data(f"/contact/v3/departments/{parse.quote(department, safe='')}", {"department_id_type":"open_department_id"})
                departments[department] = info.get("department", {}).get("name", "公司成员")
            if len(visited) > 1000:
                raise ApiError(503, "DIRECTORY_INCOMPLETE", "通讯录部门数量超出当前同步范围。")
            for page in self._pages(f"/contact/v3/departments/{parse.quote(department, safe='')}/children",
                                    {"department_id_type": "open_department_id", "fetch_child": "false", "page_size": 50}):
                for child in page.get("items", []):
                    departments[child["open_department_id"]] = child.get("name", "公司成员")
                    pending.append(child["open_department_id"])
            if has_groups and department == "0":
                continue  # Root users were read during the access check.
            for page in self._pages("/contact/v3/users/find_by_department", {"department_id": department,
                                    "department_id_type": "open_department_id", "user_id_type": "open_id", "page_size": 50}):
                for user in page.get("items", []):
                    if self._active(user) and user.get("open_id"):
                        users[user["open_id"]] = user
        return [self._profile(u, departments) for u in users.values()]

    def read_snapshot(self):
        from journey_api.department_directory import DepartmentDirectory
        profiles = self.read_profiles()
        tree = DepartmentDirectory(self).departments()
        known = {'0', *(d['id'] for d in tree)}
        names = {d['id']: d['name'] for d in tree}
        paths = {d['id']: ' / '.join(names[item] for item in d['path_ids']) for d in tree}
        paths['0'] = '公司直属'
        for profile in profiles:
            if profile['department_ids'] is None:
                raise ApiError(503, 'DIRECTORY_PERMISSION_REQUIRED', '缺少员工部门信息，请检查通讯录权限。')
            if not set(profile['department_ids']).issubset(known):
                raise ApiError(503, 'DIRECTORY_INCOMPLETE', '员工部门与组织结构暂不一致，请稍后刷新通讯录。', retryable=True)
            profile['department_paths'] = [paths[d] for d in profile['department_ids']]
        return profiles, tree

    def search(self, query):
        with self._lock:
            if self._profiles is None or time.monotonic() >= self._profiles_until:
                self._profiles = self.read_profiles()
                self._profiles_until = time.monotonic() + 120
            term = query.strip().casefold()
            matches = [u for u in self._profiles if term in u["name"].casefold()
                       or term in (u.get("employee_no") or "").casefold()]
            return {"items": matches[:30], "has_more": len(matches) > 30}


class PersistentFeishuDirectory(FeishuDirectory):
    def bulk_snapshot(self, *, include_people=True):
        from journey_api.directory_cache import bulk_snapshot
        return bulk_snapshot(self.settings, include_people=include_people)

    def search(self, query):
        from journey_api.directory_cache import search
        return search(self.settings, query)


@lru_cache
def get_directory():
    return PersistentFeishuDirectory(get_settings())
