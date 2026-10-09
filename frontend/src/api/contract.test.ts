/**
 * Contract tests: every response captured by the backend pytest contract suite must parse with the
 * schema the frontend uses for that endpoint, and every registered endpoint must have a fixture.
 */
import { fixtureSchemas } from "./fixtureSchemas";

const fixtures = import.meta.glob<{ default: unknown }>("./__fixtures__/*.json", { eager: true });
const byName = Object.fromEntries(
  Object.entries(fixtures).map(([path, mod]) => [path.replace("./__fixtures__/", "").replace(".json", ""), mod.default]),
);

describe("API contract fixtures", () => {
  it("has a fixture for every registered schema", () => {
    expect(Object.keys(fixtureSchemas).filter((name) => !(name in byName))).toEqual([]);
  });

  it("has a schema for every fixture", () => {
    expect(Object.keys(byName).filter((name) => !(name in fixtureSchemas))).toEqual([]);
  });

  for (const [name, schema] of Object.entries(fixtureSchemas)) {
    it(`parses ${name}`, () => {
      const result = schema.safeParse(byName[name]);
      if (!result.success) throw new Error(`${name}: ${JSON.stringify(result.error.issues.slice(0, 3))}`);
      expect(result.success).toBe(true);
    });
  }
});
