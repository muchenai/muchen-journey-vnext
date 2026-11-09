import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const nativeRequire = createRequire(import.meta.url);

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (Array.isArray(node)) return node.map(child => find(child, predicate)).find(Boolean) ?? null;
  return predicate(node) ? node : find(node.props?.children, predicate);
}

function createFlow(initialScreen = 'dashboard') {
  const slots = [];
  let cursor = 0;
  let href = `http://localhost:3000/app?view=${initialScreen}`;
  const calls = { assign: [], reload: 0, refresh: 0, push: 0, replace: [] };
  const historyState = { framework: 'retained' };
  const window = {
    location: { get href() { return href; }, assign(url) { calls.assign.push(url); }, reload() { calls.reload += 1; } },
    history: { state: historyState, replaceState(state, title, url) {
      assert.equal(state, historyState, 'framework history state must be preserved');
      href = String(url);
      calls.replace.push(href);
    } },
  };
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
    useRef(initial) { return slots[cursor++] ??= { current: initial }; },
    useCallback(callback) { return callback; },
    useEffect() {}, useLayoutEffect() {}, useId() { return 'test-id'; },
  };
  const ModuleHub = () => null;
  const component = () => null;
  const experience = { assignmentId: 'current-assignment', currentAssignmentId: 'current-assignment',
    stagePosition: 1, taskVersion: 1, revision: 1, status: 'AVAILABLE', materials: [],
    allowedCommands: [], journeyTasks: [], reviewFeedback: [] };
  const dependencies = {
    react,
    'next/navigation': { useRouter: () => ({ refresh() { calls.refresh += 1; }, push() { calls.push += 1; } }) },
    './index.css': {}, './loader.css': {}, './retained-controls.css': {},
    '@/lib/text-length': {}, '@/lib/feishu-client-login': {}, '../actions': {},
    './ExecutionPages': { ExecutionDetail: component, ExecutionView: component, TaskCards: component,
      executionTasks: [{ id: 'first', label: '探索启航' }] },
    './UpdatedDashboard': { UpdatedDashboard: component },
    './ModuleHub': { ModuleHub },
    './useCanvasScale': { useCanvasScale: () => 0.8 },
    './SelfCheckHistory': { SelfCheckHistory: component },
    './TaskFeedbackDialog': { TaskFeedbackDialog: component },
    './useWorkspaceRecovery': { useWorkspaceRecovery: () => ({ record: '', updateRecord() {},
      selfCheckInFlight: { current: false }, beginSelfCheck() {}, finishSelfCheck() {} }) },
    './journey-context': { JourneyProvider: component,
      useJourney: () => ({ learnerName: '真实学员', experience, initialScreen, joinPhase: 'invite', joinError: '' }),
      useTaskStatus: () => () => 'active' },
    './EntryLoader': { ProjectResourceLoader: component },
  };
  const input = readFileSync(new URL('../src/app/project29/App.tsx', import.meta.url), 'utf8')
    + '\nexport const returnProbe = { ExperienceScreen, Tasks, ClickBurst };';
  const source = ts.transpileModule(input, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, window, URL,
    require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name) });
  const { ExperienceScreen, Tasks, ClickBurst } = compiledModule.exports.returnProbe;
  return { calls, ModuleHub, ClickBurst, experience, get href() { return href; },
    render() { cursor = 0; return ExperienceScreen(); },
    returnButton() {
      const button = find(Tasks(), node => node.type === 'button' && node.props['data-node-id'] === '2006:454');
      assert.ok(button, 'the actual task list must expose its return button');
      assert.equal(button.props['data-action'], 'dashboard');
      return { textContent: '返回主页面', dataset: { action: button.props['data-action'], nodeId: '2006:454' } };
    },
  };
}

test('exploration task list returns to the retained dashboard without document or router navigation', async () => {
  for (const initialScreen of ['dashboard', 'tasks']) {
    const flow = createFlow(initialScreen);
    let tree = flow.render();
    const firstWrapper = tree.props.children[0];
    const firstModule = firstWrapper.props.children;
    assert.equal(firstModule.type, flow.ModuleHub);
    for (let pass = 0; pass < 2; pass++) {
      const currentModule = find(tree, node => node.type === flow.ModuleHub);
      currentModule.props.onExplorationMenu('tasks');
      tree = flow.render();
      const wrapper = tree.props.children[0];
      assert.equal(wrapper.type, firstWrapper.type);
      assert.equal(wrapper.key, firstWrapper.key);
      assert.equal(wrapper.props.hidden, true);
      assert.equal(wrapper.props.children.type, firstModule.type);
      assert.equal(wrapper.props.children.key, firstModule.key);
      assert.equal(wrapper.props.children.props.active, false);
      assert.equal(new URL(flow.href).searchParams.get('view'), 'tasks');
      const taskPage = find(tree, node => node.type === 'main' && node.props['data-screen'] === 'tasks');
      assert.ok(taskPage);
      const button = flow.returnButton();
      await taskPage.props.onClick({ clientX: 10, clientY: 10, target: { closest: () => button } });
      tree = flow.render();
      assert.equal(tree.props.children[0].type, firstWrapper.type);
      assert.equal(tree.props.children[0].props.hidden, false);
      const returned = tree.props.children[0].props.children;
      assert.equal(returned.type, firstModule.type);
      assert.equal(returned.key, firstModule.key);
      assert.equal(returned.props.active, true);
      assert.equal(returned.props.module, 'dashboard');
      assert.equal(new URL(flow.href).pathname, '/app');
      assert.equal(new URL(flow.href).searchParams.get('view'), 'dashboard');
      assert.equal(find(tree, node => node.type === 'main'), null);
    }
    assert.deepEqual(flow.calls.assign, []);
    assert.equal(flow.calls.reload, 0);
    assert.equal(flow.calls.push, 0);
    assert.equal(flow.calls.refresh, 0);
  }
});

test('opening a real assignment still loads its server-backed execution route', async () => {
  for (const button of [
    { textContent: '开始执行', dataset: { action: 'open-task', taskIndex: '0' } },
    { textContent: '继续当前任务', dataset: { action: 'true' } },
  ]) {
    const flow = createFlow('tasks');
    const tree = flow.render();
    const taskPage = find(tree, node => node.type === 'main');
    await taskPage.props.onClick({ clientX: 10, clientY: 10, target: { closest: () => button } });
    assert.deepEqual(flow.calls.assign, ['/app/tasks/current-assignment']);
    assert.deepEqual(flow.calls.replace, []);
  }
  const detail = createFlow('detail');
  const taskDetail = find(detail.render(), node => node.type === 'main');
  const returnButton = { textContent: '返回任务列表', dataset: { action: 'true' } };
  await taskDetail.props.onClick({ clientX: 10, clientY: 10, target: { closest: () => returnButton } });
  assert.deepEqual(detail.calls.assign, ['/app?view=tasks']);
  assert.deepEqual(detail.calls.replace, []);
});

test('return navigation clears click ripples while ordinary in-page clicks retain their feedback', async () => {
  for (const legacyTextAction of [false, true]) {
    const flow = createFlow('tasks');
    let tree = flow.render();
    let taskPage = find(tree, node => node.type === 'main');
    const ordinaryButton = { textContent: '暂未开放', dataset: { action: 'unavailable' } };
    await taskPage.props.onClick({ clientX: 120, clientY: 80, target: { closest: () => ordinaryButton } });
    tree = flow.render();
    taskPage = find(tree, node => node.type === 'main');
    assert.ok(find(taskPage, node => node.type === flow.ClickBurst), 'ordinary in-page clicks keep their feedback');
    assert.deepEqual(flow.calls.replace, [], 'feedback alone must not navigate');
    const returnButton = legacyTextAction
      ? { textContent: '返回主页面', dataset: { action: 'true' } }
      : flow.returnButton();
    await taskPage.props.onClick({ clientX: 200, clientY: 160, target: { closest: () => returnButton } });
    tree = flow.render();
    const dashboard = find(tree, node => node.type === flow.ModuleHub);
    assert.equal(dashboard.props.active, true);
    assert.equal(dashboard.props.module, 'dashboard');
    assert.equal(find(dashboard.props.dashboardContent, node => node.type === flow.ClickBurst), null,
      'the returned dashboard must not display either the previous ripple or a new return-button ripple');
    assert.deepEqual(flow.calls.assign, []);

    const dashboardPage = find(dashboard.props.dashboardContent, node => typeof node.props?.onClick === 'function');
    await dashboardPage.props.onClick({ clientX: 300, clientY: 240, target: { closest: () => ordinaryButton } });
    tree = flow.render();
    const afterClick = find(tree, node => node.type === flow.ModuleHub);
    assert.ok(find(afterClick.props.dashboardContent, node => node.type === flow.ClickBurst),
      'dashboard in-page feedback must still work after return');
    afterClick.props.onExplorationMenu('tasks');
    tree = flow.render();
    assert.equal(find(tree, node => node.type === flow.ClickBurst), null,
      'leaving through the exploration menu must also clear a preceding ripple');
    assert.equal(find(find(tree, node => node.type === flow.ModuleHub).props.dashboardContent,
      node => node.type === flow.ClickBurst), null);
  }
});

function createModuleFlow(moduleName = 'dashboard') {
  const slots = [];
  let cursor = 0;
  const calls = [];
  const ModuleSidebar = () => null;
  const ModuleHeader = () => null;
  const DeliveryLab = () => null;
  const GuildGrowthPage = () => null;
  const component = () => null;
  const dependencies = {
    react: {
      Fragment: Symbol.for('react.fragment'),
      useState(initial) {
        const index = cursor++;
        if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
        return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
      },
      useRef(initial) { return slots[cursor++] ??= { current: initial }; },
      useCallback(callback) { return callback; }, useEffect() {}, useLayoutEffect() {},
    },
    './useVillageTasks': { isVillageTaskClaimed: task => task.claimed ?? task.status !== 'available', useVillageTasks: () => ({ tasks: [], loading: false, error: null }) },
    './useCanvasScale': { useCanvasScale: () => 0.8 },
    './sharedAsset': { sharedAsset: path => path },
    './taskDepartments': { filterDepartmentTasks: tasks => tasks, taskDepartmentName: name => name },
    './moduleDemoData': { moduleTitles: {} },
    './deliveryLabModel': { createDeliveryLabSession: () => ({ status: 'available', answers: {} }) },
    './DeliveryLab': { DeliveryLab },
    './GuildGrowthPage': { GuildGrowthPage },
    '../actions': {}, './favoriteKnowledge.css': {}, './moduleHub.css': {},
  };
  for (const [file, names] of Object.entries({
    BadgeShop: ['BadgeShop'], TaskClassifications: ['TaskClassifications'], WelcomeNameDialog: ['WelcomeNameDialog'],
    ModuleShell: ['ModuleBorderProvider', 'ModuleHero', 'ModuleHeader', 'ModuleIcon', 'ModulePanel', 'ModuleSidebar', 'ModuleStatus'],
    VillageTaskCard: ['VillageTaskCard', 'VillageTaskRewards'], VillageTaskForm: ['VillageTaskForm'], VillageTaskMaterials: ['VillageTaskMaterials'], JourneyDialogSurface: ['JourneyDialogSurface'],
    AccountSwitchDialog: ['AccountSwitchDialog'], PersonalProfile: ['PersonalProfile'], WorldMap: ['WorldMap'],
    KnowledgeLibrary: ['KnowledgeLibrary'], FavoriteKnowledge: ['FavoriteKnowledge', 'KnowledgeSaveButton'],
    ModuleCourseArtwork: ['ModuleCourseArtwork'], AcademyLearning: ['AcademyLearning'],
  })) dependencies[`./${file}`] = Object.fromEntries(names.map(name => [name, component]));
  Object.assign(dependencies['./ModuleShell'], { ModuleSidebar, ModuleHeader });
  const source = ts.transpileModule(readFileSync(new URL('../src/app/project29/ModuleHub.tsx', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(source, { module: loaded, exports: loaded.exports,
    require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name) });
  const render = (active = true) => {
    cursor = 0;
    return loaded.exports.ModuleHub({ active, module: moduleName, identity: '真实学员', onNavigate() {},
      onExplorationMenu: menu => calls.push(menu), decoration: null, activeNavigationDecoration: null,
      idleNavigationDecoration: null, dashboardContent: 'retained-dashboard' });
  };
  return { render, calls, ModuleSidebar, ModuleHeader, DeliveryLab, GuildGrowthPage };
}

test('opening exploration tasks from a secondary section prepares the retained hall for return', () => {
  const { render, calls, ModuleSidebar, ModuleHeader } = createModuleFlow();
  for (const section of ['map', 'knowledge', 'profile']) {
    let tree = render();
    if (section === 'profile') find(tree, node => node.type === ModuleHeader).props.onProfile();
    else find(tree, node => node.type === ModuleSidebar).props.onMenu(section);
    tree = render();
    assert.equal(find(tree, node => node.type === ModuleHeader).props.menu, section);
    find(tree, node => node.type === ModuleHeader).props.onQuery('搜索资料');
    tree = render();
    find(tree, node => node.type === ModuleSidebar).props.onMenu('tasks');
    render(false);
    tree = render(true);
    assert.equal(find(tree, node => node.type === ModuleSidebar).props.activeMenu, 'hall');
    assert.equal(find(tree, node => node.type === ModuleHeader).props.query, '');
    assert.equal(find(tree, node => node.props?.className === 'module-dashboard-content').props.children, 'retained-dashboard');
  }
  assert.deepEqual(calls, ['tasks', 'tasks', 'tasks']);
});

test('guild lab is available to real learners and retains search and work across hall navigation', () => {
  const { render, ModuleSidebar, ModuleHeader, DeliveryLab } = createModuleFlow('guild');
  let tree = render();
  find(tree, node => node.type === ModuleSidebar).props.onMenu('lab');
  tree = render();
  let lab = find(tree, node => node.type === DeliveryLab);
  assert.ok(lab, 'a real learner can enter the simulation lab without local preview flags');
  assert.equal(find(tree, node => node.type === ModuleSidebar).props.activeMenu, 'lab');
  assert.equal(find(tree, node => node.props?.className === 'module-page-content').props['data-delivery-lab'], true);

  const session = { ...lab.props.session, status: 'active', answers: { brief: { artifact: '已保存的需求澄清草稿' } } };
  lab.props.onChange(session);
  find(tree, node => node.type === ModuleHeader).props.onQuery('数据准备');
  tree = render();
  lab = find(tree, node => node.type === DeliveryLab);
  assert.ok(lab, 'searching lab stages must keep the learner inside the lab');
  assert.equal(lab.props.query, '数据准备');
  assert.equal(lab.props.session, session);
  lab.props.onClearSearch();
  tree = render();
  assert.equal(find(tree, node => node.type === ModuleHeader).props.query, '');

  find(tree, node => node.type === ModuleSidebar).props.onMenu('hall');
  tree = render();
  assert.equal(find(tree, node => node.type === DeliveryLab), null);
  assert.equal(find(tree, node => node.type === ModuleSidebar).props.activeMenu, 'hall');
  find(tree, node => node.type === ModuleSidebar).props.onMenu('lab');
  tree = render();
  assert.equal(find(tree, node => node.type === DeliveryLab).props.session, session,
    'returning to the lab must preserve this session\'s draft and progress');
});

test('guild certification opens the real ability map without preview mode', () => {
  const { render, ModuleSidebar, GuildGrowthPage } = createModuleFlow('guild');
  let tree = render();
  find(tree, node => node.type === ModuleSidebar).props.onMenu('certification');
  tree = render();
  const page = find(tree, node => node.type === GuildGrowthPage);
  assert.ok(page, 'certification uses real persisted guild growth');
  assert.equal(page.props.view, 'certification');
  assert.equal(page.props.identity, '真实学员');
  assert.equal(find(tree, node => node.type === ModuleSidebar).props.activeMenu, 'certification');
});
