import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const nativeRequire = createRequire(import.meta.url);
const files = new URL('../src/app/project29/', import.meta.url);

function loadComponent(file, dependencies) {
  const source = ts.transpileModule(readFileSync(new URL(file, files), 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(source, {
    module: compiledModule, exports: compiledModule.exports,
    require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name),
  });
  return compiledModule.exports;
}

function createWelcomeFlow() {
  const slots = [];
  let cursor = 0;
  let effects = [];
  const element = {
    open: false, modalOpenCount: 0,
    showModal() { this.open = true; this.modalOpenCount += 1; },
    close() { this.open = false; },
  };
  const dialogReact = {
    useRef(initial) {
      const position = cursor++;
      return slots[position] ??= { current: initial };
    },
    useState(initial) {
      const position = cursor++;
      slots[position] ??= { value: initial };
      return [slots[position].value, value => { slots[position].value = value; }];
    },
    useEffect(effect, dependencies) {
      const position = cursor++;
      const previous = slots[position];
      if (!previous || dependencies.some((value, index) => !Object.is(value, previous.dependencies[index]))) {
        effects.push(() => {
          previous?.cleanup?.();
          slots[position] = { dependencies, cleanup: effect() };
        });
      }
    },
  };
  const { WelcomeNameDialog } = loadComponent('WelcomeNameDialog.tsx', { react: dialogReact });
  const component = () => null;
  const dependencies = {
    react: {
      Fragment: Symbol.for('react.fragment'),
      useState: value => [typeof value === 'function' ? value() : value, () => {}],
      useRef: value => ({ current: value }),
      useCallback: callback => callback,
      useEffect() {}, useLayoutEffect() {},
    },
    './WelcomeNameDialog': { WelcomeNameDialog },
    './useVillageTasks': { isVillageTaskClaimed: task => task.claimed ?? task.status !== 'available', useVillageTasks: () => ({ tasks: [], loading: false, error: null }) },
    './useCanvasScale': { useCanvasScale: () => 1 },
    './sharedAsset': { sharedAsset: name => name },
    './taskDepartments': { filterDepartmentTasks: tasks => tasks, taskDepartmentName: name => name },
    './deliveryLabModel': { createDeliveryLabSession: () => ({ status: 'available', answers: {} }) },
    './moduleDemoData': { moduleTitles: { village: '新手村', academy: 'AI学院', guild: '交付线公会' } },
    '../actions': { saveLearnerNickname: async () => ({}) },
    './favoriteKnowledge.css': {}, './moduleHub.css': {},
  };
  for (const [file, names] of Object.entries({
    BadgeShop: ['BadgeShop'], TaskClassifications: ['TaskClassifications'],
    ModuleShell: ['ModuleBorderProvider', 'ModuleHero', 'ModuleHeader', 'ModuleIcon', 'ModulePanel', 'ModuleSidebar', 'ModuleStatus'],
    VillageTaskCard: ['VillageTaskCard', 'VillageTaskRewards'], VillageTaskForm: ['VillageTaskForm'], VillageTaskMaterials: ['VillageTaskMaterials'], JourneyDialogSurface: ['JourneyDialogSurface'],
    AccountSwitchDialog: ['AccountSwitchDialog'], PersonalProfile: ['PersonalProfile'], WorldMap: ['WorldMap'],
    KnowledgeLibrary: ['KnowledgeLibrary'], FavoriteKnowledge: ['FavoriteKnowledge', 'KnowledgeSaveButton'],
    ModuleCourseArtwork: ['ModuleCourseArtwork'], AcademyLearning: ['AcademyLearning'], DeliveryLab: ['DeliveryLab'], GuildGrowthPage: ['GuildGrowthPage'],
  })) dependencies[`./${file}`] = Object.fromEntries(names.map(name => [name, component]));
  const { ModuleHub } = loadComponent('ModuleHub.tsx', dependencies);

  function findNameDialog(node) {
    if (!node || typeof node !== 'object') return null;
    if (Array.isArray(node)) return node.map(findNameDialog).find(Boolean) ?? null;
    if (node.type === WelcomeNameDialog) return node;
    return findNameDialog(node.props?.children);
  }
  return {
    element,
    render({ active, nicknameRequired }) {
      const tree = ModuleHub({ active, nicknameRequired, module: 'dashboard', identity: '探索者',
        onNavigate() {}, onExplorationMenu() {}, decoration: null,
        activeNavigationDecoration: null, idleNavigationDecoration: null });
      const dialog = findNameDialog(tree);
      assert.ok(dialog, 'the retained module keeps its nickname dialog mounted');
      cursor = 0;
      effects = [];
      const rendered = WelcomeNameDialog(dialog.props);
      rendered.props.ref.current = element;
      effects.forEach(effect => effect());
    },
  };
}

test('new learner welcome screen cannot open a modal from the hidden retained module', () => {
  const flow = createWelcomeFlow();
  flow.render({ active: false, nicknameRequired: true });
  assert.equal(flow.element.open, false);
  assert.equal(flow.element.modalOpenCount, 0, 'welcome buttons must remain outside any modal lock');
});

test('entering the module opens required name setup, and leaving closes the native modal', () => {
  const flow = createWelcomeFlow();
  flow.render({ active: false, nicknameRequired: true });
  flow.render({ active: true, nicknameRequired: true });
  assert.equal(flow.element.open, true);
  assert.equal(flow.element.modalOpenCount, 1);
  flow.render({ active: false, nicknameRequired: true });
  assert.equal(flow.element.open, false, 'retaining ModuleHub must not retain a blocking modal');
  flow.render({ active: true, nicknameRequired: true });
  assert.equal(flow.element.open, true);
  assert.equal(flow.element.modalOpenCount, 2);
});

test('saving a nickname closes its modal and later navigation does not reopen it', () => {
  const flow = createWelcomeFlow();
  flow.render({ active: true, nicknameRequired: true });
  assert.equal(flow.element.open, true);
  flow.render({ active: true, nicknameRequired: false });
  assert.equal(flow.element.open, false);
  flow.render({ active: false, nicknameRequired: false });
  flow.render({ active: true, nicknameRequired: false });
  assert.equal(flow.element.open, false);
  assert.equal(flow.element.modalOpenCount, 1);
});
