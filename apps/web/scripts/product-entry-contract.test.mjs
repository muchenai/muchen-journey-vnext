// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const learnerLayout = await readFile(
  new URL("../src/app/app/layout.tsx", import.meta.url),
  "utf8",
);
const product = JSON.parse(
  await readFile(new URL("../../../config/muchen_journey_product.json", import.meta.url), "utf8"),
);
const generatedProduct = JSON.parse(
  await readFile(
    new URL("../src/lib/muchen-journey-product.generated.json", import.meta.url),
    "utf8",
  ),
);
const controlledRelease = JSON.parse(
  await readFile(
    new URL("../../../config/muchen_journey_2026_09_01_controlled_release.json", import.meta.url),
    "utf8",
  ),
);
const generatedControlledRelease = JSON.parse(
  await readFile(
    new URL("../src/lib/muchen-journey-controlled-release.generated.json", import.meta.url),
    "utf8",
  ),
);
const contract = JSON.parse(
  await readFile(
    new URL("../../../outputs/controller-integration/shared-home/contract.json", import.meta.url),
    "utf8",
  ),
);


test("the deployable web projection cannot drift from the controller product contract", () => {
  assert.equal(generatedProduct.generated_from, "config/muchen_journey_product.json");
  assert.equal(generatedProduct.current_map, product.current_map);
  assert.deepEqual(
    generatedProduct.maps,
    product.maps.map(({ order, key, name, mission, people_ai_output }) => ({
      order,
      key,
      name,
      mission,
      people_ai_output,
    })),
  );
  assert.deepEqual(
    generatedProduct.approved_product_modules,
    {
      model: product.approved_product_modules.model,
      recorded_on: product.approved_product_modules.recorded_on,
      modules: product.approved_product_modules.modules,
    },
  );
});



test("the deployable controlled release projection cannot expand the frozen owner scope", () => {
  assert.equal(
    generatedControlledRelease.generated_from,
    "config/muchen_journey_2026_09_01_controlled_release.json",
  );
  assert.deepEqual(generatedControlledRelease.modules, controlledRelease.modules);
  assert.deepEqual(
    generatedControlledRelease.shared_vertical_slice,
    controlledRelease.shared_vertical_slice,
  );
  assert.equal(generatedControlledRelease.cohort_limit, 25);
  assert.equal(generatedControlledRelease.full_product_release, false);
  assert.equal(generatedControlledRelease.release_authorized, false);
});





test("homepage styles expose three responsive widths, focus, touch, and reduced motion", () => {
  assert.match(styles, /\.shared-home/);
  assert.match(styles, /@media \(max-width: 900px\)/);
  assert.match(styles, /@media \(max-width: 640px\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: no-preference\)/);
  assert.match(styles, /\.home-primary-action \{[^}]*min-height: 52px/s);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /min-width: 0/);
});

test("staff and build-stage language do not compete with the learner action", () => {
  assert.doesNotMatch(layout, /href="\/app">我的旅程/);
  assert.doesNotMatch(home, /Reviewer|return_to=%2Fops|>运营</);
  assert.doesNotMatch(layout, /vNext|Alpha/);
});
